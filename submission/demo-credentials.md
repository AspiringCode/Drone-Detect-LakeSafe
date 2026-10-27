# LakeSafe judge demo credentials

**[Open LakeSafe](https://lakesafe.vercel.app)** · [Sign in](https://lakesafe.vercel.app/login) · [Full walkthrough and setup](judge-setup.md)

These shared fictional accounts are intentionally public and work through **December 31, 2026, Pacific time**. Access expires January 1, 2027 at 00:00 America/Los_Angeles (08:00 UTC). No email verification or one-time code is needed for these prepared accounts.

| Account | Email | Password | Access |
|---|---|---|---|
| JUDGE_ALL | `judge_all@lakesafe.example.test` | `LS-demo-fsFz2F3Qgz2xJhj80BMCJeN6` | All three demo lakes |
| JUDGE_LS | `judge_ls@lakesafe.example.test` | `LS-demo-1oEqZkEX02FVO_vd2wZi-3C9` | Lake Sammamish only |
| JUDGE_BL | `judge_bl@lakesafe.example.test` | `LS-demo-KWc-62gsXRjUXVjSuqMyIPoS` | Beaver Lake only |
| JUDGE_PL | `judge_pl@lakesafe.example.test` | `LS-demo-3-zvDjP5866urOThfLlkuVKU` | Pine Lake only |

Use **JUDGE_ALL** for the complete software demonstration. The other accounts demonstrate access limited to one lake. Paste the email and password exactly into the sign-in form.

## Walkthrough

1. Explore the public lake page without signing in, then select **Sign in** and sign in using an account above.
2. Open **Lakes** and choose an available lake card. Each card opens a separate simulation workspace.
3. Choose **Start simulation**, **Add simulated drone**, then **Regenerate zones** so two drones patrol separate zones.
4. Choose a **Demo second-drone finding**, then **Simulate detection**. Review the initial detection and the investigating drone's separate finding. Arrival alone does not corroborate a detection.
5. **Confirm detection** keeps the investigation open. **Dismiss and resume patrol** or **End investigation and resume patrol** returns the simulated drones to their original patrols.
6. Review the session's records in **Alerts** and **Reports**. Choose **Stop simulation** when finished.

## Scope and limits

These accounts can read their demo workspaces, run simulated patrols, and review simulated alerts. They cannot register or command physical drones, change flight-safety settings, add lakes, manage members, or publish public lake pages. The demo stations contain no real devices and cannot accept real-device registrations.

Simulation workspaces are shared: another judge may change or stop the same simulation. State and session history may reset when the API restarts. Findings are generated scenarios, not camera observations; no emergency service is contacted. Keep the **SIMULATED** labels visible in recordings.

Private administrator accounts, hardware demonstrations, and device credentials remain separate. Do not use these passwords for any other service. Ordinary operator enrollment still requires verification, MFA, active station membership, and the appropriate role. Public signup does not grant operational access.
