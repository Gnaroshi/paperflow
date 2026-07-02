#!/usr/bin/env bash
set -euo pipefail

echo "PaperFlow distribution readiness"
echo

echo "Code signing identities:"
security find-identity -v -p codesigning || true
echo

if security find-identity -v -p codesigning | grep -q "Developer ID Application:"; then
  echo "Developer ID Application certificate: found"
else
  echo "Developer ID Application certificate: missing"
  echo "Apple Development certificates are not enough for public download distribution."
  echo "Create and install a Developer ID Application certificate in Apple Developer."
fi

echo
echo "Notary profiles:"
if xcrun notarytool history --keychain-profile "${NOTARY_PROFILE:-paperflow-notary}" >/dev/null 2>&1; then
  echo "Notary profile '${NOTARY_PROFILE:-paperflow-notary}': usable"
else
  echo "Notary profile '${NOTARY_PROFILE:-paperflow-notary}': not configured or not usable"
  echo "Create one with: xcrun notarytool store-credentials paperflow-notary"
fi

echo
echo "Local install target:"
if [[ -d /Applications/PaperFlow.app ]]; then
  echo "/Applications/PaperFlow.app: installed"
else
  echo "/Applications/PaperFlow.app: not installed"
fi
