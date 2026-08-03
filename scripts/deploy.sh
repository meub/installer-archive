#!/usr/bin/env bash
# Deploy site/ to the standard S3 + CloudFront setup.
# Requires: aws cli configured, and S3_BUCKET / CF_DISTRIBUTION_ID set (env or below).
set -euo pipefail
cd "$(dirname "$0")/.."

S3_BUCKET="${S3_BUCKET:-installerarchive.alexmeub.com}"
CF_DISTRIBUTION_ID="${CF_DISTRIBUTION_ID:-E2WF0FL59J3X6E}"

# Long-ish cache for static assets, short for the entry point + data.
aws s3 sync site/ "s3://$S3_BUCKET/" --delete \
  --exclude "index.html" --exclude "data/*" \
  --cache-control "public, max-age=86400"
aws s3 sync site/ "s3://$S3_BUCKET/" \
  --exclude "*" --include "index.html" --include "data/*" \
  --cache-control "public, max-age=300, must-revalidate"

aws cloudfront create-invalidation --distribution-id "$CF_DISTRIBUTION_ID" --paths "/*" >/dev/null
echo "Deployed to s3://$S3_BUCKET and invalidated CloudFront."
