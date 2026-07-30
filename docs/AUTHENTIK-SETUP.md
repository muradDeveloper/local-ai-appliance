# Authentik OIDC Setup for Open WebUI

This guide documents the steps to configure Authentik 2026.5.x as the OpenID Connect identity provider for Open WebUI. Open WebUI is configured for OIDC-only login — there is no native signup form. All users must exist in Authentik before they can log in.

## Prerequisites

The following containers must be running and healthy before starting:

- `ai-authentik-server` — the Authentik admin UI must be reachable at `https://auth.murs-local.net`
- `ai-authentik-worker` — required for background tasks (email, flows). If not running, start it after fixing the healthcheck `start_period` (see known issue in `docs/handoffs/`).
- `ai-postgres` — Authentik database backend

Log in to `https://auth.murs-local.net/if/admin/` as `akadmin` using the `AUTHENTIK_BOOTSTRAP_PASSWORD` from `.env`.

---

## Step 1: Create the OAuth2/OpenID Provider

The provider defines how Open WebUI authenticates against Authentik.

1. In the left sidebar, expand **Applications** and click **Providers**.
2. Click **New Provider**.
3. In the **Create New Provider** wizard, select **OAuth2/OpenID Provider** and click **Next**.
4. Fill in the provider form:

   | Field | Value |
   |---|---|
   | Provider Name | `Open WebUI OIDC` |
   | Authorization Flow | Select the default explicit-consent flow (type the name into the combobox, then **click the matching option from the dropdown** — do not just press Enter) |
   | Client Type | `Confidential` (default) |
   | Client ID | `open-webui-client` |

5. Scroll down to **Redirect URIs/Origins (RegEx)**. Click **Add entry** and configure:

   | Field | Value |
   |---|---|
   | Mode | `Strict` |
   | Type | `Authorization` |
   | URI | `https://ai.murs-local.net/oauth/oidc/callback` |

6. Click **Create**.

The provider is created and appears in the Providers list with a warning: "Provider not assigned to any application." This is expected — the application is linked in the next step.

---

## Step 2: Create and Link the Application

> **Important gotcha:** The **New Application** wizard accessed from the *Applications* page creates a brand-new provider alongside the application. It does **not** allow you to select an existing provider. To link to the provider created in Step 1, you must use the **New Application** button on the *provider's detail page* instead.

1. Click the **Open WebUI OIDC** provider name in the Providers list to open its detail page.
2. Under **Assigned to application**, click the blue **New Application** button.
3. Fill in the application form:

   | Field | Value |
   |---|---|
   | Application Name | `Open WebUI` |
   | Slug | `open-webui` |
   | Provider | `Open WebUI OIDC` (pre-filled) |

   > **Slug gotcha:** Authentik auto-populates the slug field as `open-web-ui` (with hyphens) when you type the display name. You must manually correct this to `open-webui` (no hyphen between "web" and "ui"). The slug must match the value Open WebUI uses internally for OIDC discovery.

4. Leave all other fields at their defaults (Group: empty, Policy engine mode: ANY).
5. Click **Create Application**.

The provider detail page now shows **Assigned to application: Open WebUI**. The yellow warning banner is gone. The provider detail page also confirms the endpoint URLs:

- Authorize URL: `https://auth.murs-local.net/application/o/authorize/`
- Token URL: `https://auth.murs-local.net/application/o/token/`
- Userinfo URL: `https://auth.murs-local.net/application/o/userinfo/`

---

## Step 3: Copy the Client Secret

The client secret is generated when the provider is created. Retrieve it before leaving the provider detail page.

1. On the **Open WebUI OIDC** provider detail page, scroll down to **Related actions** and click **Edit**.
2. In the edit form, scroll to the **Client Secret** field. Click the copy icon or reveal button and copy the full secret string.
3. On the server, open `.env` and set:

   ```
   OAUTH_CLIENT_SECRET=<paste the secret here>
   ```

4. Close the edit dialog.

The client secret is only shown in full in the edit form. If you lose it, you can regenerate it by editing the provider and clicking the refresh button next to the secret field (this will invalidate existing sessions).

---

## Step 4: Create Groups

Open WebUI uses Authentik group membership to assign roles. Two groups are required:

| Group | Open WebUI role | Controlled by env var |
|---|---|---|
| `ai-admins` | Admin | `OAUTH_ADMIN_ROLES=ai-admins` |
| `ai-users` | User | `OAUTH_ALLOWED_ROLES=ai-admins,ai-users` |

Create both groups:

1. In the left sidebar, expand **Directory** and click **Groups**.
2. Click **New Group**.
3. Enter Group Name: `ai-admins`. Leave **Superuser Privileges** off. Click **Create Group**.
4. Repeat to create `ai-users`.

Both groups now appear in the Groups list alongside the default Authentik groups.

---

## Step 5: Create Users and Assign Groups

All users who need to log into Open WebUI must be created in Authentik. Open WebUI has no self-registration.

### Create a user

1. In the left sidebar, click **Users**.
2. Click **New User**.
3. Select **Internal User** and click **Next**.
4. Fill in the user details:

   | Field | Value |
   |---|---|
   | Username | e.g. `mursadmin` |
   | Display Name | e.g. `Murad` |
   | Email Address | optional |
   | Active | enabled (default) |
   | Path | `users` (default) |

5. Click **Create**.

Repeat for each user.

### Assign users to groups

1. Navigate to **Directory > Groups** and click the group name (e.g. `ai-admins`).
2. Click the **Users** tab.
3. Click **Add Existing User**.
4. Search for and select the user(s) to add. Click **Add**.

Repeat for the other group.

**Final group membership for this deployment:**

| Group | Members |
|---|---|
| `ai-admins` | `akadmin` (authentik Default Admin), `mursadmin` |
| `ai-users` | `murs`, `alaa` |

---

## Step 6: Set User Passwords

Newly created users have no password and cannot log in until one is set.

1. Navigate to **Directory > Users** and click the username link to open the user's detail page.
2. Under **Recovery**, click **Set password**.
3. Enter and confirm a password. Click **Set password**.

Repeat for each user.

Users can also change their own password via the Authentik user interface at `https://auth.murs-local.net/if/user/`.

---

## Bring Up Open WebUI

Once the client secret is in `.env` and all users are configured, start Open WebUI:

```bash
docker compose up -d open-webui
```

---

## Verification

After Open WebUI starts:

1. Navigate to `https://ai.murs-local.net` in a browser.
2. You should be redirected to the Authentik login page. There is no native Open WebUI login form.
3. Log in as `mursadmin`. After authentication, Authentik shows an explicit-consent screen listing the permissions Open WebUI is requesting. Click **Allow**.
4. You are redirected back to Open WebUI. Confirm you land on the admin interface (mursadmin is in `ai-admins`).
5. Log out and log in as `murs`. Confirm you land on the standard user interface.
6. Confirm neither `murs` nor `alaa` can access admin settings in Open WebUI.

If login fails with an OIDC error, check:

- `OAUTH_CLIENT_SECRET` in `.env` matches the value in Authentik's provider edit form
- The redirect URI in Authentik matches `https://ai.murs-local.net/oauth/oidc/callback` exactly (Strict mode)
- The application slug in Authentik is `open-webui` (not `open-web-ui`)
- Open WebUI container was restarted after updating `.env`

---

## Compose environment variables (reference)

These variables in `compose.yml` wire Open WebUI to Authentik:

```yaml
ENABLE_OAUTH_SIGNUP: "true"
OAUTH_PROVIDER_NAME: "authentik"
OPENID_PROVIDER_URL: "https://auth.murs-local.net/application/o/open-webui/.well-known/openid-configuration"
OAUTH_CLIENT_ID: "open-webui-client"
OAUTH_CLIENT_SECRET: "${OAUTH_CLIENT_SECRET}"
OAUTH_SCOPES: "openid email profile"
OAUTH_ADMIN_ROLES: "ai-admins"
OAUTH_ALLOWED_ROLES: "ai-admins,ai-users"
```

These variables in the Authentik server service must not be removed (Authentik 2026.5.x changed its default listen address to `[::]` — IPv6 — which breaks on IPv6-disabled hosts):

```yaml
AUTHENTIK_LISTEN__HTTP: "0.0.0.0:9000"
AUTHENTIK_LISTEN__HTTPS: "0.0.0.0:9443"
```
