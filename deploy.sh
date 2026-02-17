#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./deploy.sh dev
#   ./deploy.sh prod

ENVIRONMENT="${1:-}"
if [[ -z "$ENVIRONMENT" ]]; then
  echo "Usage: $0 {dev|prod}"
  exit 1
fi

PROFILE="personal"
ZIP_NAME="deploy.zip"
BUILD_DIR="build"
REQ_FILE="requirements.txt"
S3_BUCKET="${S3_BUCKET:-}"

case "$ENVIRONMENT" in
  dev)
    REGION="eu-central-1"
    PRIMARY_LAMBDA_NAME="ai_bot_dev"
    TRANSCRIPT_LAMBDA_NAME="ai_bot_dev_transcript"
    DEFAULT_S3_BUCKET="ai-bot-dev-artifacts"
    ;;
  prod)
    REGION="eu-west-1"
    PRIMARY_LAMBDA_NAME="tg-gemini-bot"
    TRANSCRIPT_LAMBDA_NAME="tg-gemini-bot-transcript"
    DEFAULT_S3_BUCKET="ai-bot-prod-artifacts"
    ;;
  *)
    echo "Unknown environment '$ENVIRONMENT' (use dev or prod)"
    exit 1
    ;;
esac

if [[ -z "$S3_BUCKET" ]]; then
  S3_BUCKET="$DEFAULT_S3_BUCKET"
fi

LAMBDA_NAMES=("$PRIMARY_LAMBDA_NAME" "$TRANSCRIPT_LAMBDA_NAME")

echo "========================================"
echo "Deploying Lambda"
echo "  Env:     $ENVIRONMENT"
echo "  Region:  $REGION"
echo "  Lambdas: ${LAMBDA_NAMES[*]}"
echo "  Profile: $PROFILE"
echo "========================================"

echo "==> Cleaning build artifacts"
rm -rf "$BUILD_DIR" "$ZIP_NAME"
mkdir -p "$BUILD_DIR"

echo "==> Installing dependencies"
pip install -r "$REQ_FILE" \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  --target "$BUILD_DIR"

echo "==> Copying source files"
cp -r *.py src "$BUILD_DIR"/

echo "==> Creating deployment zip"
(
  cd "$BUILD_DIR"
  zip -r "../$ZIP_NAME" .
)

ZIP_SIZE_BYTES=$(wc -c < "$ZIP_NAME")
S3_KEY="${PRIMARY_LAMBDA_NAME}/deploy-$(date +%Y%m%d%H%M%S).zip"
echo "==> ZIP size: ${ZIP_SIZE_BYTES} bytes"
echo "==> Uploading deployment zip to s3://$S3_BUCKET/$S3_KEY"
aws s3 cp "$ZIP_NAME" "s3://$S3_BUCKET/$S3_KEY" \
  --region "$REGION" \
  --profile "$PROFILE" \
  --no-cli-pager

for lambda_name in "${LAMBDA_NAMES[@]}"; do
  echo "==> Updating $lambda_name from S3"
  aws lambda update-function-code \
    --function-name "$lambda_name" \
    --s3-bucket "$S3_BUCKET" \
    --s3-key "$S3_KEY" \
    --region "$REGION" \
    --profile "$PROFILE" \
    --no-cli-pager \
    --query 'FunctionArn' \
    --output text
done

echo "✅ Deployment complete."
