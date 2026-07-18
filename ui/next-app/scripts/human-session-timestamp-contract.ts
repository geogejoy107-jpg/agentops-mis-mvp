import {
  humanSessionTimestampExpired,
  humanThrottleTimestampActive,
  nextHumanLoginFailureState,
} from "../src/server/controlPlane/humanSession";
import { agentGatewayTimestampExpired } from "../src/server/controlPlane/auth";


function require(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

const now = Date.parse("2026-07-18T00:00:00.000Z");

require(!humanThrottleTimestampActive(null, now), "missing_throttle_timestamp_was_blocked");
require(humanThrottleTimestampActive("invalid", now), "invalid_throttle_timestamp_failed_open");
require(humanThrottleTimestampActive("2026-07-18T00:00:01.000Z", now), "future_throttle_timestamp_was_not_blocked");
require(!humanThrottleTimestampActive("2026-07-17T23:59:59.000Z", now), "past_throttle_timestamp_remained_blocked");

require(humanSessionTimestampExpired("invalid", now), "invalid_session_expiry_failed_open");
require(humanSessionTimestampExpired("2026-07-18T00:00:00.000Z", now), "boundary_session_expiry_remained_active");
require(humanSessionTimestampExpired("2026-07-17T23:59:59.000Z", now), "past_session_expiry_remained_active");
require(!humanSessionTimestampExpired("2026-07-18T00:00:01.000Z", now), "future_session_expiry_was_rejected");

require(agentGatewayTimestampExpired(null, now), "missing_gateway_session_expiry_failed_open");
require(!agentGatewayTimestampExpired(null, now, true), "non_expiring_gateway_token_was_rejected");
require(agentGatewayTimestampExpired("invalid", now), "invalid_gateway_expiry_failed_open");
require(agentGatewayTimestampExpired("2026-07-18T00:00:00.000Z", now), "boundary_gateway_expiry_remained_active");
require(!agentGatewayTimestampExpired("2026-07-18T00:00:01.000Z", now), "future_gateway_expiry_was_rejected");

const malformedWindow = nextHumanLoginFailureState({
  failure_count: 1,
  window_started_at: "invalid",
}, now);
require(malformedWindow.failedClosed && malformedWindow.count >= 8, "invalid_login_window_failed_open");
const futureWindow = nextHumanLoginFailureState({
  failure_count: 1,
  window_started_at: "2026-07-18T00:00:01.000Z",
}, now);
require(futureWindow.failedClosed && futureWindow.count >= 8, "future_login_window_failed_open");

process.stdout.write(`${JSON.stringify({
  ok: true,
  contract: "human_session_timestamp_fail_closed_v1",
  invalid_throttle_blocks: true,
  invalid_session_expires: true,
  invalid_gateway_credential_expires: true,
  missing_gateway_session_expiry_expires: true,
  malformed_login_window_blocks: true,
})}\n`);
