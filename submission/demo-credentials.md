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

## Device registration and mission workflow

These accounts have drone-administration capabilities within their assigned judge stations, including real-device registration, lake assignment, mission preview/export, patrol upload requests, retirement, and fleet safety controls. No one-time code is required for the prepared accounts.

1. Open **Drones**, choose a judge station beneath the title, then **Add drone +**.
2. Register a device public key and assign that device to the station's lake. Keep the device private key on the device; never publish it here.
3. Use the connection instructions to send signed heartbeats. Registration alone does not establish a live connection.
4. Preview the mission and download its Mission Planner `.waypoints` file. Review the route, altitude and home location before choosing **Send patrol**.
5. Inspect acknowledgement/upload status. A queued request is not confirmed delivery, and it does not arm the aircraft. The pilot retains arming and RC override.
6. The lake workspace provides **Real drone safety** controls, including **Enable real autonomy**, **Pause real autonomy**, and **Request fleet safe return**, with a required reason. Device acknowledgements determine whether the requested state is active.
7. Retire temporary devices when finished.

## Scope and limits

The accounts can use simulation and the device workflows above only within the three separate judge stations. Existing devices in the original stations remain inaccessible. Judges cannot add lakes, manage members, or publish public lake pages.

**These credentials are public and shared. Anyone using them can control a device connected to a judge station. Connect only devices you own and intend to make available for this demonstration.** Device registration creates a new credential; it does not grant access to devices already registered elsewhere.

Simulation workspaces are shared: another judge may change or stop the same simulation. State and session history may reset when the API restarts. Findings are generated scenarios, not camera observations; no emergency service is contacted. Keep the **SIMULATED** labels visible in recordings.

Private administrator accounts and original-station device credentials remain separate. Do not use these passwords for any other service. Ordinary operator enrollment still requires verification, MFA, active station membership, and the appropriate role. Public signup does not grant operational access.
