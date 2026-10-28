# LakeSafe CAC demo administrator access

**[Open LakeSafe](https://lakesafe.vercel.app)** · [Sign in](https://lakesafe.vercel.app/login) · [Judge setup and walkthrough](judge-setup.md)

Ask the maintainer for the existing administrator password. Use **ADMIN_MASTER** for the full demonstration. These existing fictional CAC administrator accounts use the original stations and remain valid through **December 31, 2026, Pacific time**. Access expires January 1, 2027 at 00:00 America/Los_Angeles (08:00 UTC).

| Account | Email | Password | Station access |
|---|---|---|---|
| ADMIN_MASTER | `admin_master@lakesafe.example.test` | `Supplied privately` | All original assigned stations and lakes |
| ADMIN_LS | `admin_ls@lakesafe.example.test` | `Supplied privately` | Lake Sammamish station |
| ADMIN_BL | `admin_bl@lakesafe.example.test` | `Supplied privately` | Beaver Lake station |
| ADMIN_PL | `admin_pl@lakesafe.example.test` | `Supplied privately` | Pine Lake station |

These administrator accounts retain their original station permissions, including device registration, mission export, patrol requests and retirement. Existing registered devices are part of that scope. Passwords are supplied privately by the maintainer. Connect or command a physical device only with its owner's authorization.

## Walkthrough

1. Open **Sign in** and use an email above and the privately supplied password. Prepared CAC accounts use a temporary password-only sign-in exception. Sensitive fleet-safety policy actions retain their existing recent-MFA check.
2. Open **Lakes** and choose an original lake card. The separate judge lake copies have been retired.
3. For a software demonstration, choose **Start simulation**, **Add simulated drone**, and **Regenerate zones**. Choose a **Demo second-drone finding** and **Simulate detection**. Review the separate finding, then confirm, dismiss or end the investigation. Dismiss/end returns simulated drones to patrol. Keep **SIMULATED** labels visible.
4. Open **Alerts** and **Reports** to review available records. Stop the simulation when finished.
5. Open **Drones**, choose the station beneath the title, then **Add drone +** for Register, Assign lake and Connect. Register only a device public key; keep its private key on the device.
6. Inspect connection status and signed heartbeats. Preview a mission and download its Mission Planner `.waypoints` file. Review the route, altitude and home location before **Send patrol**. Queuing is separate from confirmed device delivery/upload; arming and RC override remain with the pilot.
7. Use **Account > Stations > Manage station** for the account's existing member and lake-management permissions. New lakes remain private until explicitly published.

The former JUDGE_ALL/JUDGE_LS/JUDGE_BL/JUDGE_PL accounts and separate judge workspaces have been retired. Use the ADMIN accounts above.

Simulation and review history may reset when the API restarts. No emergency service is contacted by the software demonstration. Normal public signup does not grant station access. Supabase service keys, provider secrets and device private keys are not included here.
