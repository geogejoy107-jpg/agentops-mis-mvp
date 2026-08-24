import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROUTE_ROOT = join(APP_ROOT, "app/api/mis");
const CONTROL_PLANE_ROOT = join(APP_ROOT, "src/server/controlPlane");
const CONFIG_FILE = "src/server/controlPlane/config.ts";
const PROXY_FILE = "src/server/controlPlane/proxy.ts";
const CATCH_ALL_FILE = "app/api/mis/[...path]/route.ts";

const EXPECTED_PROXY_CALL_OWNERS = new Set([
  "app/api/mis/[...path]/route.ts",
  "app/api/mis/agent-gateway/approvals/request/route.ts",
  "app/api/mis/agent-gateway/prepared-actions/route.ts",
  "app/api/mis/approvals/[approvalId]/[decision]/route.ts",
  "app/api/mis/approvals/[approvalId]/route.ts",
  "app/api/mis/approvals/route.ts",
  "app/api/mis/memories/[memoryId]/[decision]/route.ts",
  "app/api/mis/memories/export/route.ts",
  "app/api/mis/memories/route.ts",
  "src/server/controlPlane/agentGatewayRoute.ts",
  "src/server/controlPlane/evidenceRouteOwner.ts",
  "src/server/controlPlane/humanAgentDetail.ts",
  "src/server/controlPlane/humanReadRoute.ts",
  "src/server/controlPlane/humanTaskOperations.ts",
  "src/server/controlPlane/humanWorkerFleetReads.ts",
]);

const FREE_LOCAL_GUARDS = new Set([
  "legacyPythonProxyAllowed",
  "explicitFreeLocalProxyMode",
]);

type ParsedSource = Readonly<{
  path: string;
  source: string;
  file: ts.SourceFile;
}>;

function fail(message: string): never {
  throw new Error(`commercial_api_ownership_contract_failed: ${message}`);
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) fail(message);
}

function sourcePath(absolutePath: string) {
  return relative(APP_ROOT, absolutePath).replaceAll("\\", "/");
}

function collectTypeScriptFiles(root: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(root).sort()) {
    const absolute = join(root, entry);
    if (statSync(absolute).isDirectory()) {
      files.push(...collectTypeScriptFiles(absolute));
    } else if (entry.endsWith(".ts") || entry.endsWith(".tsx")) {
      files.push(absolute);
    }
  }
  return files;
}

function parse(relativePath: string): ParsedSource {
  const absolutePath = join(APP_ROOT, relativePath);
  const source = readFileSync(absolutePath, "utf8");
  return {
    path: relativePath,
    source,
    file: ts.createSourceFile(
      relativePath,
      source,
      ts.ScriptTarget.Latest,
      true,
      relativePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
    ),
  };
}

function walk(node: ts.Node, visit: (candidate: ts.Node) => void) {
  visit(node);
  node.forEachChild((child) => walk(child, visit));
}

function callName(node: ts.Node): string | undefined {
  if (!ts.isCallExpression(node)) return undefined;
  if (ts.isIdentifier(node.expression)) return node.expression.text;
  if (ts.isPropertyAccessExpression(node.expression)) return node.expression.name.text;
  return undefined;
}

function directCallName(node: ts.Node): string | undefined {
  return ts.isCallExpression(node) && ts.isIdentifier(node.expression)
    ? node.expression.text
    : undefined;
}

function namedImportBindings(file: ts.SourceFile, moduleNames: ReadonlySet<string>) {
  const bindings = new Map<string, string>();
  for (const statement of file.statements) {
    if (
      !ts.isImportDeclaration(statement)
      || !ts.isStringLiteral(statement.moduleSpecifier)
      || !moduleNames.has(statement.moduleSpecifier.text)
      || !statement.importClause?.namedBindings
      || !ts.isNamedImports(statement.importClause.namedBindings)
    ) continue;
    for (const element of statement.importClause.namedBindings.elements) {
      bindings.set(element.name.text, element.propertyName?.text ?? element.name.text);
    }
  }
  return bindings;
}

function importedLocalName(
  file: ts.SourceFile,
  moduleNames: ReadonlySet<string>,
  exportedName: string,
) {
  const matches = [...namedImportBindings(file, moduleNames)].filter(
    ([, imported]) => imported === exportedName,
  );
  assert(matches.length === 1, `${file.fileName}: expected one ${exportedName} import`);
  return matches[0][0];
}

function bindingIdentifiers(name: ts.BindingName): ts.Identifier[] {
  if (ts.isIdentifier(name)) return [name];
  return name.elements.flatMap((element) =>
    ts.isOmittedExpression(element) ? [] : bindingIdentifiers(element.name));
}

function runtimeBindingIdentifiers(file: ts.SourceFile) {
  const bindings: ts.Identifier[] = [];
  walk(file, (node) => {
    if (ts.isVariableDeclaration(node) || ts.isParameter(node)) {
      bindings.push(...bindingIdentifiers(node.name));
    } else if (
      (ts.isFunctionDeclaration(node)
        || ts.isFunctionExpression(node)
        || ts.isClassDeclaration(node)
        || ts.isClassExpression(node))
      && node.name
    ) {
      bindings.push(node.name);
    } else if (ts.isCatchClause(node) && node.variableDeclaration) {
      bindings.push(...bindingIdentifiers(node.variableDeclaration.name));
    }
  });
  return bindings;
}

function assertImportedBindingUnshadowed(file: ts.SourceFile, localName: string) {
  const shadow = runtimeBindingIdentifiers(file).find((binding) => binding.text === localName);
  assert(
    !shadow,
    `${file.fileName}:${shadow ? file.getLineAndCharacterOfPosition(shadow.getStart()).line + 1 : 0}: imported binding ${localName} is shadowed`,
  );
}

function catchAllSyntaxFindings(file: ts.SourceFile) {
  const allowedModules = new Set([
    "next/server",
    "@/server/controlPlane/config",
    "@/server/controlPlane/proxy",
  ]);
  const unreviewedImports: string[] = [];
  let importEquals = false;
  let directNetworkCapability = false;
  let environmentAccess = false;
  let dynamicCodeOrImport = false;
  for (const statement of file.statements) {
    if (ts.isImportEqualsDeclaration(statement)) {
      importEquals = true;
      dynamicCodeOrImport = true;
    }
    if (
      ts.isImportDeclaration(statement)
      && ts.isStringLiteral(statement.moduleSpecifier)
      && !allowedModules.has(statement.moduleSpecifier.text)
    ) unreviewedImports.push(statement.moduleSpecifier.text);
  }
  walk(file, (node) => {
    if (
      (ts.isIdentifier(node) && [
        "fetch",
        "WebSocket",
        "XMLHttpRequest",
        "globalThis",
        "global",
        "Reflect",
      ].includes(node.text))
      || (ts.isNewExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "URL")
    ) directNetworkCapability = true;
    if (ts.isIdentifier(node) && node.text === "process") environmentAccess = true;
    if (
      (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword)
      || (ts.isIdentifier(node) && ["require", "eval", "Function"].includes(node.text))
      || (
        ts.isPropertyAccessExpression(node)
        && ["constructor", "__proto__", "prototype"].includes(node.name.text)
      )
      || (
        ts.isElementAccessExpression(node)
        && ts.isStringLiteralLike(node.argumentExpression)
        && ["constructor", "__proto__", "prototype"].includes(node.argumentExpression.text)
      )
    ) dynamicCodeOrImport = true;
  });
  return {
    directNetworkCapability,
    dynamicCodeOrImport,
    environmentAccess,
    importEquals,
    unreviewedImports,
  };
}

function callsNamed(node: ts.Node, name: string) {
  let found = false;
  walk(node, (candidate) => {
    if (callName(candidate) === name) found = true;
  });
  return found;
}

function stringLiterals(node: ts.Node) {
  const values = new Set<string>();
  walk(node, (candidate) => {
    if (ts.isStringLiteral(candidate)) values.add(candidate.text);
  });
  return values;
}

function functionNamed(file: ts.SourceFile, name: string): ts.FunctionDeclaration {
  const declaration = file.statements.find(
    (statement): statement is ts.FunctionDeclaration =>
      ts.isFunctionDeclaration(statement) && statement.name?.text === name,
  );
  assert(declaration?.body, `${file.fileName}: missing function ${name}`);
  return declaration;
}

function exitsWithoutFallthrough(node: ts.Statement): boolean {
  if (ts.isReturnStatement(node) || ts.isThrowStatement(node)) return true;
  if (ts.isBlock(node)) {
    return node.statements.some((statement) => exitsWithoutFallthrough(statement));
  }
  if (ts.isIfStatement(node)) {
    return node.elseStatement !== undefined
      && exitsWithoutFallthrough(node.thenStatement)
      && exitsWithoutFallthrough(node.elseStatement);
  }
  return false;
}

function assertExitAnalysisFailsClosed() {
  const source = ts.createSourceFile(
    "exit-analysis.ts",
    `function thenOnly(value: boolean) {
      if (value) return;
    }
    function elseOnly(value: boolean) {
      if (value) void 0;
      else return;
    }
    function complete(value: boolean) {
      if (value) return;
      else throw new Error("blocked");
    }`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const functions = source.statements.filter(ts.isFunctionDeclaration);
  assert(functions[0]?.body, "exit analysis then-only fixture missing");
  assert(functions[1]?.body, "exit analysis else-only fixture missing");
  assert(functions[2]?.body, "exit analysis complete fixture missing");
  assert(
    exitsWithoutFallthrough(functions[0].body) === false,
    "then-only termination must not dominate a proxy call",
  );
  assert(
    exitsWithoutFallthrough(functions[1].body) === false,
    "else-only termination must not dominate a proxy call",
  );
  assert(
    exitsWithoutFallthrough(functions[2].body) === true,
    "complete branch termination must be recognized",
  );
}

function assertTrustedGuardBindingFailsClosed() {
  const propertyCall = ts.createSourceFile(
    "property-call.ts",
    `import { legacyPythonProxyAllowed } from "@/server/controlPlane/config";
    const unrelated = { legacyPythonProxyAllowed: () => true };
    function probe() {
      if (!unrelated.legacyPythonProxyAllowed()) return;
    }`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const probe = functionNamed(propertyCall, "probe");
  const guard = probe.body!.statements[0];
  assert(ts.isIfStatement(guard), "property guard fixture missing");
  assert(
    negatedGuardName(guard.expression) === undefined,
    "property calls must never satisfy a canonical Free Local guard binding",
  );

  const aliasedImport = ts.createSourceFile(
    "aliased-import.ts",
    `import { legacyPythonProxyAllowed as freeLocalAllowed } from "@/server/controlPlane/config";`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  assert(
    importedLocalName(
      aliasedImport,
      new Set(["@/server/controlPlane/config"]),
      "legacyPythonProxyAllowed",
    ) === "freeLocalAllowed",
    "canonical guard import aliases must retain their module binding",
  );

  const shadowedImport = ts.createSourceFile(
    "shadowed-import.ts",
    `import { legacyPythonProxyAllowed } from "@/server/controlPlane/config";
    function probe() {
      const legacyPythonProxyAllowed = () => true;
      return legacyPythonProxyAllowed();
    }`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  let shadowRejected = false;
  try {
    assertImportedBindingUnshadowed(shadowedImport, "legacyPythonProxyAllowed");
  } catch (error) {
    shadowRejected = /imported binding legacyPythonProxyAllowed is shadowed/.test(
      String(error),
    );
  }
  assert(shadowRejected, "canonical imported guard shadowing must fail closed");

  const computedCapabilities = ts.createSourceFile(
    "computed-capabilities.ts",
    `const one = globalThis["fetch"];
    const two = Reflect.get(globalThis, "process")["env"];
    import net = require("node:net");`,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const findings = catchAllSyntaxFindings(computedCapabilities);
  assert(findings.directNetworkCapability, "computed global network capability must be detected");
  assert(findings.importEquals, "import-equals capability must be detected");
  assert(findings.dynamicCodeOrImport, "require capability must be detected");
}

function negatedGuardName(expression: ts.Expression): string | undefined {
  if (!ts.isPrefixUnaryExpression(expression) || expression.operator !== ts.SyntaxKind.ExclamationToken) {
    return undefined;
  }
  return directCallName(expression.operand);
}

function positiveGuardName(expression: ts.Expression): string | undefined {
  return directCallName(expression);
}

function isTrustedFreeLocalGuard(parsed: ParsedSource, localName: string) {
  if (localName === "explicitFreeLocalProxyMode") {
    return parsed.file.statements.some(
      (statement) => ts.isFunctionDeclaration(statement)
        && statement.name?.text === localName,
    );
  }
  const imports = namedImportBindings(
    parsed.file,
    new Set(["@/server/controlPlane/config", "./config"]),
  );
  return imports.get(localName) === "legacyPythonProxyAllowed";
}

function directChildOfBlock(node: ts.Node, block: ts.Block): ts.Statement | undefined {
  let current = node;
  while (current.parent && current.parent !== block) current = current.parent;
  return ts.isStatement(current) ? current : undefined;
}

function isFreeLocalGuardDominated(parsed: ParsedSource, call: ts.CallExpression) {
  let current: ts.Node | undefined = call;
  while (current?.parent) {
    const parent: ts.Node = current.parent;
    if (ts.isIfStatement(parent) && parent.thenStatement === current) {
      const guard = positiveGuardName(parent.expression);
      if (
        guard
        && FREE_LOCAL_GUARDS.has(guard)
        && isTrustedFreeLocalGuard(parsed, guard)
      ) return true;
    }
    if (ts.isBlock(parent)) {
      const child = directChildOfBlock(call, parent);
      const index = child ? parent.statements.indexOf(child) : -1;
      for (let cursor = 0; cursor < index; cursor += 1) {
        const statement = parent.statements[cursor];
        if (!ts.isIfStatement(statement)) continue;
        const guard = negatedGuardName(statement.expression);
        if (
          guard
          && FREE_LOCAL_GUARDS.has(guard)
          && isTrustedFreeLocalGuard(parsed, guard)
          && exitsWithoutFallthrough(statement.thenStatement)
        ) {
          return true;
        }
      }
    }
    current = parent;
  }
  return false;
}

function assertDeploymentModeBoundary() {
  const parsed = parse(CONFIG_FILE);
  const sourceFile = parsed.file;
  const freeModes = sourceFile.statements.find(
    (statement) => ts.isVariableStatement(statement)
      && statement.declarationList.declarations.some(
        (declaration) => ts.isIdentifier(declaration.name)
          && declaration.name.text === "FREE_LOCAL_DEPLOYMENT_MODES",
      ),
  );
  const productionModes = sourceFile.statements.find(
    (statement) => ts.isVariableStatement(statement)
      && statement.declarationList.declarations.some(
        (declaration) => ts.isIdentifier(declaration.name)
          && declaration.name.text === "PRODUCTION_DEPLOYMENT_MODES",
      ),
  );
  assert(freeModes, `${CONFIG_FILE}: FREE_LOCAL_DEPLOYMENT_MODES missing`);
  assert(productionModes, `${CONFIG_FILE}: PRODUCTION_DEPLOYMENT_MODES missing`);
  const freeValues = stringLiterals(freeModes);
  const productionValues = stringLiterals(productionModes);
  assert(freeValues.has("free_local"), `${CONFIG_FILE}: free_local must remain explicit`);
  for (const mode of ["production", "prod", "shared", "hosted"]) {
    assert(productionValues.has(mode), `${CONFIG_FILE}: ${mode} must remain a production mode`);
    assert(!freeValues.has(mode), `${CONFIG_FILE}: ${mode} cannot be a Free Local mode`);
  }

  const controlPlaneMode = functionNamed(sourceFile, "controlPlaneMode");
  const modeText = controlPlaneMode.body!.getText(sourceFile).replace(/\s+/g, "");
  const productionFallback = 'isProductionDeployment()?"postgres":"proxy"';
  assert(
    modeText.split(productionFallback).length - 1 >= 2,
    `${CONFIG_FILE}: configured proxy and default mode must both resolve production to postgres`,
  );

  const legacyAllowed = functionNamed(sourceFile, "legacyPythonProxyAllowed");
  const returns = legacyAllowed.body!.statements.filter(ts.isReturnStatement);
  assert(returns.length === 1 && returns[0].expression, `${CONFIG_FILE}: legacy proxy guard shape changed`);
  const legacyText = returns[0].expression!.getText(sourceFile).replace(/\s+/g, "");
  assert(
    legacyText === '!isProductionDeployment()&&controlPlaneMode()==="proxy"',
    `${CONFIG_FILE}: legacy Python proxy must require non-production proxy mode`,
  );
}

function assertExplicitFreeLocalGuard(parsed: ParsedSource) {
  const declaration = functionNamed(parsed.file, "explicitFreeLocalProxyMode");
  const text = declaration.body!.getText(parsed.file).replace(/\s+/g, "");
  assert(text.includes("AGENTOPS_DEPLOYMENT_MODE"), `${parsed.path}: explicit guard lacks deployment mode`);
  assert(text.includes('==="free_local"'), `${parsed.path}: explicit guard must require free_local`);
  assert(text.includes("AGENTOPS_CONTROL_PLANE_MODE"), `${parsed.path}: explicit guard lacks control-plane mode`);
  assert(text.includes("AGENTOPS_TS_CONTROL_PLANE_MODE"), `${parsed.path}: explicit guard lacks legacy control-plane alias`);
  assert(text.includes('==="proxy"'), `${parsed.path}: explicit guard must require proxy mode`);
  assert(callsNamed(declaration, "trim") && callsNamed(declaration, "toLowerCase"), `${parsed.path}: explicit guard must normalize modes`);
  assert(text.includes("&&"), `${parsed.path}: explicit guard must require both mode predicates`);
}

function assertProxyHelperFailsClosed() {
  const parsed = parse(PROXY_FILE);
  const declaration = functionNamed(parsed.file, "proxyControlPlaneRequest");
  const statements = declaration.body!.statements;
  assert(statements.length > 1, `${PROXY_FILE}: proxy helper body is incomplete`);
  const guard = statements[0];
  assert(ts.isIfStatement(guard), `${PROXY_FILE}: Free Local rejection must be the first operation`);
  const legacyGuard = importedLocalName(
    parsed.file,
    new Set(["./config"]),
    "legacyPythonProxyAllowed",
  );
  assertImportedBindingUnshadowed(parsed.file, legacyGuard);
  assert(
    negatedGuardName(guard.expression) === legacyGuard,
    `${PROXY_FILE}: first guard must require the canonical Free Local mode predicate`,
  );
  assert(exitsWithoutFallthrough(guard.thenStatement), `${PROXY_FILE}: Free Local guard must return before I/O`);
  assert(callsNamed(guard.thenStatement, "json"), `${PROXY_FILE}: Free Local guard must emit a bounded rejection`);
  assert(
    stringLiterals(guard.thenStatement).has("typescript_route_owner_required"),
    `${PROXY_FILE}: production rejection code changed`,
  );
  assert(
    declaration.body!.statements.slice(1).some((statement) => callsNamed(statement, "request")),
    `${PROXY_FILE}: expected Python upstream transport is no longer structurally identified`,
  );
}

function assertCatchAllFailsClosed() {
  const parsed = parse(CATCH_ALL_FILE);
  const proxyBinding = importedLocalName(
    parsed.file,
    new Set(["@/server/controlPlane/proxy"]),
    "proxyControlPlaneRequest",
  );
  const legacyGuard = importedLocalName(
    parsed.file,
    new Set(["@/server/controlPlane/config"]),
    "legacyPythonProxyAllowed",
  );
  assertImportedBindingUnshadowed(parsed.file, proxyBinding);
  assertImportedBindingUnshadowed(parsed.file, legacyGuard);
  const findings = catchAllSyntaxFindings(parsed.file);
  assert(!findings.importEquals, `${CATCH_ALL_FILE}: import-equals capabilities are forbidden`);
  assert(
    findings.unreviewedImports.length === 0,
    `${CATCH_ALL_FILE}: unreviewed import capability ${findings.unreviewedImports.join(", ")}`,
  );
  assert(!findings.directNetworkCapability, `${CATCH_ALL_FILE}: catch-all cannot own network globals or URL construction`);
  assert(!findings.environmentAccess, `${CATCH_ALL_FILE}: catch-all cannot access process state`);
  assert(!findings.dynamicCodeOrImport, `${CATCH_ALL_FILE}: catch-all cannot dynamically obtain capabilities`);
  const declaration = functionNamed(parsed.file, "proxy");
  const statements = declaration.body!.statements;
  const transportIndex = statements.findIndex((statement) => {
    let found = false;
    walk(statement, (node) => {
      if (directCallName(node) === proxyBinding) found = true;
    });
    return found;
  });
  assert(transportIndex > 0, `${CATCH_ALL_FILE}: catch-all transport call missing`);
  const guardIndex = statements.findIndex((statement) => {
    if (!ts.isIfStatement(statement)) return false;
    return negatedGuardName(statement.expression) === legacyGuard
      && exitsWithoutFallthrough(statement.thenStatement);
  });
  assert(guardIndex >= 0 && guardIndex < transportIndex, `${CATCH_ALL_FILE}: catch-all transport is not dominated by the Free Local guard`);
  for (const method of ["GET", "POST"]) {
    const exported = parsed.file.statements.find((statement) =>
      ts.isVariableStatement(statement)
      && statement.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword)
      && statement.declarationList.declarations.some((declaration) =>
        ts.isIdentifier(declaration.name)
        && declaration.name.text === method
        && declaration.initializer?.getText(parsed.file) === "proxy"),
    );
    assert(exported, `${CATCH_ALL_FILE}: ${method} must remain owned by the guarded catch-all`);
  }
}

function assertProxyCallOwnership() {
  const candidates = [
    ...collectTypeScriptFiles(ROUTE_ROOT),
    ...collectTypeScriptFiles(CONTROL_PLANE_ROOT),
  ];
  const actualOwners = new Set<string>();
  let guardedCalls = 0;

  for (const absolutePath of candidates) {
    const path = sourcePath(absolutePath);
    if (path === PROXY_FILE) continue;
    const parsed = parse(path);
    const proxyImports = namedImportBindings(
      parsed.file,
      new Set(["@/server/controlPlane/proxy", "./proxy"]),
    );
    const proxyBindings = new Set(
      [...proxyImports].filter(([, imported]) => imported === "proxyControlPlaneRequest").map(([local]) => local),
    );
    for (const binding of proxyBindings) {
      assertImportedBindingUnshadowed(parsed.file, binding);
    }
    const calls: ts.CallExpression[] = [];
    walk(parsed.file, (node) => {
      const name = directCallName(node);
      if (ts.isCallExpression(node) && name && proxyBindings.has(name)) {
        calls.push(node);
      }
    });
    if (calls.length === 0) continue;
    actualOwners.add(path);
    if (calls.some((call) => {
      let current: ts.Node | undefined = call;
      while (current) {
        if (ts.isFunctionDeclaration(current) && current.name?.text === "explicitFreeLocalProxyMode") {
          return true;
        }
        current = current.parent;
      }
      return false;
    })) {
      fail(`${path}: explicit guard must not invoke the proxy itself`);
    }
    if (parsed.source.includes("function explicitFreeLocalProxyMode")) {
      assertExplicitFreeLocalGuard(parsed);
    }
    for (const call of calls) {
      assert(
        isFreeLocalGuardDominated(parsed, call),
        `${path}:${parsed.file.getLineAndCharacterOfPosition(call.getStart()).line + 1}: Python proxy call is not dominated by a Free Local guard`,
      );
      guardedCalls += 1;
    }
  }

  const unexpected = [...actualOwners].filter((owner) => !EXPECTED_PROXY_CALL_OWNERS.has(owner));
  const missing = [...EXPECTED_PROXY_CALL_OWNERS].filter((owner) => !actualOwners.has(owner));
  assert(unexpected.length === 0, `unreviewed Python proxy owners: ${unexpected.join(", ")}`);
  assert(missing.length === 0, `expected proxy owners disappeared without contract review: ${missing.join(", ")}`);
  assert(guardedCalls > 0, "no guarded compatibility proxy calls were inspected");
  return { owners: actualOwners.size, guardedCalls };
}

function assertMigrationLedgerCoverage(coverage: Readonly<{
  owners: number;
  guardedCalls: number;
}>) {
  const ledger = readFileSync(resolve(
    APP_ROOT,
    "../../docs/COMMERCIAL_MIGRATION_CLEAN_ROOM_BREAKDOWN.md",
  ), "utf8");
  const recordedCoverage = new RegExp(
    `current coverage is ${coverage.owners} owner files and `
      + `${coverage.guardedCalls} Free Local-guarded\\s+calls\\.`,
  );
  assert(
    recordedCoverage.test(ledger),
    "commercial migration ledger proxy coverage is stale",
  );
}

function main() {
  assertExitAnalysisFailsClosed();
  assertTrustedGuardBindingFailsClosed();
  assertDeploymentModeBoundary();
  assertProxyHelperFailsClosed();
  assertCatchAllFailsClosed();
  const coverage = assertProxyCallOwnership();
  assertMigrationLedgerCoverage(coverage);
  process.stdout.write(`${JSON.stringify({
    contract: "commercial_api_ownership_v1",
    production_shared_postgres_owner_required: true,
    catch_all_python_fallback_fail_closed: true,
    free_local_python_compatibility_preserved: true,
    migration_ledger_coverage_bound: true,
    proxy_owner_files: coverage.owners,
    guarded_proxy_calls: coverage.guardedCalls,
  })}\n`);
}

main();
