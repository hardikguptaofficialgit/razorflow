# Publish RazorFlow SDK (security-key / 2FA accounts)

npm CLI cannot use a physical security key interactively. Use a **Granular Access Token** instead.

## Step 1 — Create token (one time)

1. Open https://www.npmjs.com/settings/hardik21232323/tokens
2. **Generate New Token** → **Granular Access Token**
3. Name: `razorflow-sdk-publish`
4. Expiration: 90 days (or your preference)
5. Packages: **Read and write** for all packages (or select the three razorflow packages)
6. Permissions: enable **Publish** (and Read if needed)
7. Copy the token (starts with `npm_...`) — shown only once

## Step 2 — Publish from PowerShell

```powershell
cd "c:\Disk E\Razorpay"
$env:NPM_TOKEN = "npm_paste_your_token_here"
.\packages\publish-sdk.ps1
```

Or pass OTP if you also have an authenticator app configured:

```powershell
npm publish -w @hardik21232323/razorflow-protocol --access public --otp=123456
npm publish -w @hardik21232323/razorflow-browser --access public --otp=123456
npm publish -w @hardik21232323/razorflow-client --access public --otp=123456
```

## Published package names

- `@hardik21232323/razorflow-protocol`
- `@hardik21232323/razorflow-browser`
- `@hardik21232323/razorflow-client`
