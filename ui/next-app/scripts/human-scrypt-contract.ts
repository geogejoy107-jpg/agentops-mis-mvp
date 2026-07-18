import { scrypt as scryptCallback } from "node:crypto";

import {
  humanScryptWorkCountForTests,
  resetHumanScryptWorkCountForTests,
  verifyHumanLoginPassword,
  type HumanLoginCredentialForVerification,
} from "../src/server/controlPlane/humanSession";

function scrypt(password: string, salt: Buffer) {
  return new Promise<Buffer>((resolve, reject) => {
    scryptCallback(password, salt, 32, { N: 16_384, r: 8, p: 1, maxmem: 128 * 1024 * 1024 }, (error, value) => {
      if (error) reject(error);
      else resolve(value as Buffer);
    });
  });
}

const password = "Synthetic-contract-password";
const salt = Buffer.from("4ccb1f63fb74452858aa784349f90f01", "hex");
const hash = await scrypt(password, salt);
const credential: HumanLoginCredentialForVerification = {
  credential_id: "hcred_contract",
  user_id: "husr_contract",
  name: "Contract User",
  username: "contract-user",
  password_hash: hash.toString("hex"),
  password_salt: salt.toString("hex"),
  password_params_json: JSON.stringify({ name: "scrypt", n: 16_384, r: 8, p: 1, keylen: 32 }),
  credential_status: "active",
};

process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = "synthetic-contract-hmac-key-with-more-than-32-bytes";
resetHumanScryptWorkCountForTests();
const results = [
  await verifyHumanLoginPassword("Wrong-contract-password", credential),
  await verifyHumanLoginPassword("Wrong-contract-password", undefined),
  await verifyHumanLoginPassword("short", undefined),
  await verifyHumanLoginPassword("Wrong-contract-password", {
    ...credential,
    credential_status: "disabled",
  }),
];
const workCount = humanScryptWorkCountForTests();
const ok = results.every((value) => value === false) && workCount === results.length;
process.stdout.write(`${JSON.stringify({
  ok,
  contract: "human_login_scrypt_constant_work_v1",
  attempts: results.length,
  scrypt_work_count: workCount,
  credential_values_omitted: true,
})}\n`);
if (!ok) process.exitCode = 1;
