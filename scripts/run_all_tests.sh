#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────
# run_all_tests.sh, runs the test suite for all three MakeItSo
# platforms (desktop, android, ios) and writes a combined summary to
# test-results/latest.md.
#
# Each platform is run independently: if one platform's toolchain
# isn't available (no JDK 17, no Xcode, etc.) or a platform has no
# test target configured yet, that section is reported as such in
# the summary instead of aborting the whole run.
#
# Usage:
#   scripts/run_all_tests.sh              # run all 3 platforms, combined report
#   scripts/run_all_tests.sh desktop      # run just one platform (used by CI,
#   scripts/run_all_tests.sh android      # where each job only has that one
#   scripts/run_all_tests.sh ios          # platform's toolchain installed)
# ───────────────────────────────────────────────────────────────────
set -uo pipefail

WHICH="${1:-all}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/test-results"
RAW_DIR="$OUT_DIR/raw"
if [ "$WHICH" = "all" ]; then
  REPORT="$OUT_DIR/latest.md"
else
  REPORT="$OUT_DIR/latest-${WHICH}.md"
fi

mkdir -p "$RAW_DIR"

TIMESTAMP="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"

DESKTOP_STATUS="?"; DESKTOP_SUMMARY="not run"; DESKTOP_FAILURES=""
ANDROID_STATUS="?"; ANDROID_SUMMARY="not run"; ANDROID_FAILURES=""
IOS_STATUS="?"; IOS_SUMMARY="not run"; IOS_FAILURES=""

# ── Desktop (Python / unittest) ──────────────────────────────────
run_desktop() {
  echo "==> Running desktop tests"
  local log="$RAW_DIR/desktop.log"
  # Prefer desktop/.venv's interpreter when it exists: desktop's
  # requirements.txt (pyyaml, etc.) is installed there, and running
  # discovery against a bare system python3 that lacks those deps
  # produces spurious test failures (e.g. routines.py silently
  # degrading to "no routines loaded" when `import yaml` fails) that
  # look like real regressions but are just a missing-dependency
  # false alarm.
  local desktop_python="$REPO_ROOT/desktop/.venv/bin/python3"
  if [ ! -x "$desktop_python" ]; then
    desktop_python="python3"
  fi
  ( cd "$REPO_ROOT" && "$desktop_python" -m unittest discover -s desktop/tests -v ) > "$log" 2>&1
  local exit_code=$?

  local ran_line
  ran_line="$(grep -E "^Ran [0-9]+ tests?" "$log" | tail -1)"
  local total
  total="$(echo "$ran_line" | grep -oE "[0-9]+" | head -1)"
  total="${total:-0}"

  if grep -qE "^OK" "$log"; then
    DESKTOP_STATUS="PASS"
    DESKTOP_SUMMARY="${total} passed, 0 failed"
  elif grep -qE "^FAILED" "$log"; then
    local fail_line
    fail_line="$(grep -E "^FAILED" "$log" | tail -1)"
    local failures errors
    failures="$(echo "$fail_line" | grep -oE "failures=[0-9]+" | grep -oE "[0-9]+")"
    errors="$(echo "$fail_line" | grep -oE "errors=[0-9]+" | grep -oE "[0-9]+")"
    failures="${failures:-0}"; errors="${errors:-0}"
    local bad=$((failures + errors))
    DESKTOP_STATUS="FAIL"
    DESKTOP_SUMMARY="$((total - bad)) passed, ${bad} failed (failures=${failures}, errors=${errors})"
    DESKTOP_FAILURES="$(grep -E "^(FAIL|ERROR): " "$log")"
  else
    DESKTOP_STATUS="ERROR"
    DESKTOP_SUMMARY="test run did not complete (exit code ${exit_code}), see raw/desktop.log"
  fi
}

# ── Android (Kotlin / gradle unit tests) ─────────────────────────
run_android() {
  echo "==> Running android tests"
  local log="$RAW_DIR/android.log"
  ( cd "$REPO_ROOT/android" && chmod +x gradlew && ./gradlew testDebugUnitTest --console=plain ) > "$log" 2>&1
  local exit_code=$?

  local xml_dir="$REPO_ROOT/android/app/build/test-results/testDebugUnitTest"
  local total=0 failures=0 errors=0 skipped=0
  local found_xml=0
  if [ -d "$xml_dir" ]; then
    for f in "$xml_dir"/TEST-*.xml; do
      [ -e "$f" ] || continue
      found_xml=1
      local t f_ e_ s_
      t="$(grep -oE 'tests="[0-9]+"' "$f" | head -1 | grep -oE '[0-9]+')"
      f_="$(grep -oE 'failures="[0-9]+"' "$f" | head -1 | grep -oE '[0-9]+')"
      e_="$(grep -oE 'errors="[0-9]+"' "$f" | head -1 | grep -oE '[0-9]+')"
      s_="$(grep -oE 'skipped="[0-9]+"' "$f" | head -1 | grep -oE '[0-9]+')"
      total=$((total + ${t:-0}))
      failures=$((failures + ${f_:-0}))
      errors=$((errors + ${e_:-0}))
      skipped=$((skipped + ${s_:-0}))
    done
  fi

  if [ "$found_xml" -eq 1 ]; then
    local bad=$((failures + errors))
    if [ "$bad" -eq 0 ]; then
      ANDROID_STATUS="PASS"
    else
      ANDROID_STATUS="FAIL"
      ANDROID_FAILURES="$(grep -B1 "<failure" "$xml_dir"/TEST-*.xml 2>/dev/null | grep -E "testcase name" )"
    fi
    ANDROID_SUMMARY="$((total - bad)) passed, ${bad} failed, ${skipped} skipped (of ${total} total)"
  elif [ "$exit_code" -eq 0 ]; then
    ANDROID_STATUS="PASS"
    ANDROID_SUMMARY="build succeeded, but no unit test sources exist yet under android/app/src/test, 0 tests run"
  else
    ANDROID_STATUS="ERROR"
    ANDROID_SUMMARY="build/test run failed (exit code ${exit_code}) before producing test results, see raw/android.log"
    ANDROID_FAILURES="$(tail -15 "$log")"
  fi
}

# ── iOS (Swift / XCTest via xcodebuild) ──────────────────────────
run_ios() {
  echo "==> Running iOS tests"
  local log="$RAW_DIR/ios.log"
  local ios_dir="$REPO_ROOT/ios/MakeItSo"

  if ! command -v xcodebuild >/dev/null 2>&1; then
    IOS_STATUS="SKIPPED"
    IOS_SUMMARY="xcodebuild not available on this machine (requires macOS + Xcode)"
    return
  fi

  ( cd "$ios_dir" && command -v xcodegen >/dev/null 2>&1 && xcodegen generate ) > "$log" 2>&1

  local sim_name
  sim_name="$(xcrun simctl list devices available 2>/dev/null | grep -oE "iPhone [A-Za-z0-9 ]+ \(" | head -1 | sed 's/ ($//')"
  sim_name="${sim_name:-iPhone 16}"

  ( cd "$ios_dir" && xcodebuild test -scheme MakeItSo -sdk iphonesimulator \
      -destination "platform=iOS Simulator,name=${sim_name}" ) >> "$log" 2>&1
  local exit_code=$?

  if grep -q "is not currently configured for the test action" "$log"; then
    IOS_STATUS="SKIPPED"
    IOS_SUMMARY="no XCTest target configured in project.yml yet, 0 tests run (build-only verification exists in CI)"
  elif [ "$exit_code" -eq 0 ] && grep -q "TEST SUCCEEDED" "$log"; then
    IOS_STATUS="PASS"
    local exec_line
    exec_line="$(grep -E "Executed [0-9]+ test" "$log" | tail -1)"
    IOS_SUMMARY="${exec_line:-all tests passed}"
  elif grep -qE "TEST FAILED|Executed [0-9]+ test.*with [1-9][0-9]* failure" "$log"; then
    IOS_STATUS="FAIL"
    IOS_SUMMARY="$(grep -E "Executed [0-9]+ test" "$log" | tail -1)"
    IOS_FAILURES="$(grep -E "error:.*XCTAssert|^    .*failed \(" "$log")"
  else
    IOS_STATUS="ERROR"
    IOS_SUMMARY="test run did not complete cleanly (exit code ${exit_code}), see raw/ios.log"
  fi
}

case "$WHICH" in
  desktop) run_desktop ;;
  android) run_android ;;
  ios)     run_ios ;;
  all)     run_desktop; run_android; run_ios ;;
  *)       echo "Usage: $0 [desktop|android|ios|all]" >&2; exit 2 ;;
esac

# ── Write report (combined, or just the one platform that ran) ──
{
  echo "# Test Results, $TIMESTAMP"
  echo
  echo "| Platform | Status | Summary |"
  echo "|---|---|---|"
  if [ "$WHICH" = "all" ] || [ "$WHICH" = "desktop" ]; then
    echo "| Desktop (Python) | ${DESKTOP_STATUS} | ${DESKTOP_SUMMARY} |"
  fi
  if [ "$WHICH" = "all" ] || [ "$WHICH" = "android" ]; then
    echo "| Android (Kotlin) | ${ANDROID_STATUS} | ${ANDROID_SUMMARY} |"
  fi
  if [ "$WHICH" = "all" ] || [ "$WHICH" = "ios" ]; then
    echo "| iOS (Swift) | ${IOS_STATUS} | ${IOS_SUMMARY} |"
  fi
  echo

  if [ -n "$DESKTOP_FAILURES" ]; then
    echo "## Desktop failures"
    echo '```'
    echo "$DESKTOP_FAILURES"
    echo '```'
    echo
  fi

  if [ -n "$ANDROID_FAILURES" ]; then
    echo "## Android failures"
    echo '```'
    echo "$ANDROID_FAILURES"
    echo '```'
    echo
  fi

  if [ -n "$IOS_FAILURES" ]; then
    echo "## iOS failures"
    echo '```'
    echo "$IOS_FAILURES"
    echo '```'
    echo
  fi

  echo "Raw logs: \`test-results/raw/{desktop,android,ios}.log\`"
} > "$REPORT"

echo "==> Wrote $REPORT"
cat "$REPORT"

# Exit non-zero if any platform actually failed (not just skipped/no-tests).
if [ "$DESKTOP_STATUS" = "FAIL" ] || [ "$ANDROID_STATUS" = "FAIL" ] || [ "$IOS_STATUS" = "FAIL" ]; then
  exit 1
fi
exit 0
