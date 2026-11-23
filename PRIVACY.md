# Privacy policy

For the Google app **n8n local gtm-pipeline**, used by this repository's demo build. Last updated 23/11/2026.

## Who uses it

Only the owner of this repository. The app connects the owner's own n8n, running on their own computer, to their own Google account. It is a portfolio demo, not a service offered to anyone else.

## What it can reach in Google

The app asks for three permissions. Because one of them is the email address, Google also adds its standard sign-in permission, `openid`, shown as "Associate you with your personal info on Google". Nothing else is granted.

| Permission | What the app does with it |
|---|---|
| Send email on your behalf (`gmail.send`) | Sends one short email per demo lead to the owner's own inbox. It cannot read, change or delete any mail |
| Only the Drive files this app creates (`drive.file`) | Creates one tracking spreadsheet and adds rows to it. It cannot see any other file |
| Your primary email address (`userinfo.email`) | Reads the signed-in account's address at run time, so the email goes to the owner's own inbox and no address is stored in the workflow |
| Sign-in (`openid`), added by Google | Links the login to the Google account. The app uses nothing from it beyond the email address above |

## What data it handles

- **Demo leads.** Made up and company-level only: invented company names, `.example` web domains, and short invented enquiries. No real people and no contact details.
- **The owner's email address.** Read from Google when the workflow runs, used as the recipient, and not written to the spreadsheet, the repository or any export.

## Where data goes

- Tracking rows go to one spreadsheet in the owner's Google Drive, private to the owner.
- Emails go to the owner's own inbox.
- n8n keeps run records on the owner's computer.
- Nothing is sold, shared, used for advertising, or used to train AI models.

## Google API Services User Data Policy

The app's use of information received from Google APIs follows the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

## Removing access

The owner can remove the app's access at any time in their Google Account, under Security, "Your connections to third-party apps and services". The spreadsheet can be deleted from Google Drive, and the n8n run records from n8n.

## Changes and contact

Changes to this page are kept in the repository's history. Questions can be raised as an issue on this repository.
