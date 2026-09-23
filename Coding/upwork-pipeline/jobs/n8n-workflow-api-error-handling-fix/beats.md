# Loom beat sheet (30 to 90 seconds, glanced at, never read aloud)

- you want it reliable and easy to maintain, this is that pattern
- Validate Schema and Required Fields, bad ones get Reject With Field Errors
- System A: Fetch Related Record fails, Back Off 30 Seconds, try again
- retries used up, Fallback: Queue for Manual Retry, nothing gets dropped
- Map Fields Between Systems, then System B: Create or Update Record
- Run Log: Status, Latency, Retries, one readable row per run
- retry count and backoff get tuned to your api, not guessed
- can start [START], working demo by [DRAFT]
