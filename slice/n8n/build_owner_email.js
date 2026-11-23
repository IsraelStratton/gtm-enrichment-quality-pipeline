// Build owner email (n8n slice, chapter 3).
// The recipient is read at run time from the connected Google account, so no
// address sits in this workflow or its export, and no payload can change it.
const inbox = $input.item.json.email;
if (!inbox || !inbox.includes('@')) {
  throw new Error('Google returned no email address. Check the Google credential.');
}
const at = inbox.lastIndexOf('@');
const to = `${inbox.slice(0, at)}+gtm-slice${inbox.slice(at)}`;

const row = $('Shape tracking row').item.json;
const lead = $('Approved lead in').item.json.body;

// Base64url without Buffer or btoa, so it runs in any n8n Code sandbox.
function base64Url(str) {
  const bytes = unescape(encodeURIComponent(str));
  const abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const n = (bytes.charCodeAt(i) << 16) | ((bytes.charCodeAt(i + 1) || 0) << 8) | (bytes.charCodeAt(i + 2) || 0);
    out += abc[(n >> 18) & 63] + abc[(n >> 12) & 63];
    if (i + 1 < bytes.length) out += abc[(n >> 6) & 63];
    if (i + 2 < bytes.length) out += abc[n & 63];
  }
  return out;
}

// Plain ASCII headers go as they are; anything else is RFC 2047 encoded.
function header(value) {
  if (/^[\x20-\x7E]*$/.test(value)) return value;
  let b64 = base64Url(value).replace(/-/g, '+').replace(/_/g, '/');
  while (b64.length % 4) b64 += '=';
  return `=?UTF-8?B?${b64}?=`;
}

const subject = `Approved lead for ${row.owner_team}: ${row.company_name} (${row.priority})`;
const text = [
  `${row.company_name} (${row.domain}) is approved for ${row.owner_team}.`,
  '',
  `Route: ${row.route}`,
  `Priority: ${row.priority}`,
  `Industry: ${lead.industry}`,
  `Enquiry: ${lead.enquiry}`,
  `Reason: ${lead.reason}`,
  `Decision: ${row.decision} by ${row.approved_by} at ${row.approved_at}`,
  '',
  `Run: ${row.run_id}`,
  'Sent by the n8n slice. Made-up demo data.',
].join('\r\n');

const mime = [
  `To: ${to}`,
  `Subject: ${header(subject)}`,
  'MIME-Version: 1.0',
  'Content-Type: text/plain; charset="UTF-8"',
  'Content-Transfer-Encoding: 8bit',
  '',
  text,
].join('\r\n');

return { json: { raw: base64Url(mime), subject } };
