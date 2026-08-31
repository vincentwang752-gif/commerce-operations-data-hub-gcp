const STATUS_HEADER = 'Klaviyo Sync Status';
const SYNCED_AT_HEADER = 'Klaviyo Synced At';
const DETAIL_HEADER = 'Klaviyo Sync Detail';

function onVocFormSubmit(e) {
  const props = PropertiesService.getScriptProperties();
  const endpoint = props.getProperty('VOC_ENDPOINT');
  const token = props.getProperty('VOC_WEBHOOK_TOKEN');
  const stage = Number(props.getProperty('VOC_STAGE'));
  const invokerServiceAccount = props.getProperty('VOC_INVOKER_SERVICE_ACCOUNT');

  if (!endpoint || !token || !invokerServiceAccount || ![1, 2].includes(stage)) {
    throw new Error('Missing Cloud Run endpoint, webhook token, invoker service account, or valid survey stage.');
  }

  const sheet = e.range.getSheet();
  const row = e.range.getRow();
  const lastColumn = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  const values = sheet.getRange(row, 1, 1, lastColumn).getDisplayValues()[0];
  const record = {};
  headers.forEach((header, index) => record[String(header).trim()] = values[index]);

  const email = firstValue(record, ['邮箱', '电子邮件地址', 'Email', 'email']);
  const completedAt = firstValue(record, ['时间戳记', '时间戳', 'Timestamp', 'timestamp']) || new Date().toISOString();
  const responseId = [SpreadsheetApp.getActive().getId(), sheet.getSheetId(), row].join(':');

  ensureStatusColumns(sheet, headers);
  writeStatus(sheet, row, 'PROCESSING', '', 'Sent to Google Cloud');

  try {
    const identityToken = getCloudRunIdentityToken(endpoint, invokerServiceAccount);
    const response = UrlFetchApp.fetch(endpoint.replace(/\/$/, '') + '/form-submit', {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + identityToken,
        'X-VOC-Token': token
      },
      payload: JSON.stringify({
        stage: stage,
        email: email,
        completed_at: completedAt,
        response_id: responseId,
        spreadsheet_id: SpreadsheetApp.getActive().getId(),
        sheet_id: sheet.getSheetId(),
        row_number: row
      }),
      muteHttpExceptions: true
    });

    const statusCode = response.getResponseCode();
    let body = {};
    try {
      body = JSON.parse(response.getContentText() || '{}');
    } catch (parseError) {
      body = {error: response.getContentText().slice(0, 300)};
    }

    const status = body.status || (statusCode >= 200 && statusCode < 300 ? 'SYNCED' : 'ERROR');
    const detail = [
      'GCP HTTP ' + statusCode,
      body.order_id ? 'order=' + body.order_id : '',
      body.lifecycle_id ? 'lifecycle=' + body.lifecycle_id : '',
      body.error || ''
    ].filter(Boolean).join(' | ');
    writeStatus(sheet, row, status, new Date(), detail);

    if (statusCode < 200 || statusCode >= 300) {
      throw new Error(detail);
    }
  } catch (error) {
    writeStatus(sheet, row, 'ERROR', new Date(), String(error).slice(0, 500));
    throw error;
  }
}

function getCloudRunIdentityToken(endpoint, serviceAccountEmail) {
  const audience = endpoint.replace(/\/$/, '');
  const url = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/' +
    encodeURIComponent(serviceAccountEmail) + ':generateIdToken';
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {'Authorization': 'Bearer ' + ScriptApp.getOAuthToken()},
    payload: JSON.stringify({audience: audience, includeEmail: true}),
    muteHttpExceptions: true
  });
  if (response.getResponseCode() !== 200) {
    throw new Error('Unable to create Cloud Run identity token: HTTP ' +
      response.getResponseCode() + ' ' + response.getContentText().slice(0, 300));
  }
  return JSON.parse(response.getContentText()).token;
}

function firstValue(record, aliases) {
  for (const alias of aliases) {
    if (record[alias]) return String(record[alias]).trim();
  }
  return '';
}

function ensureStatusColumns(sheet, currentHeaders) {
  const required = [STATUS_HEADER, SYNCED_AT_HEADER, DETAIL_HEADER];
  const existing = new Set(currentHeaders.map(value => String(value).trim()));
  let column = sheet.getLastColumn() + 1;
  required.forEach(header => {
    if (!existing.has(header)) {
      sheet.getRange(1, column).setValue(header);
      column += 1;
    }
  });
}

function writeStatus(sheet, row, status, syncedAt, detail) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  const positions = {};
  headers.forEach((header, index) => positions[String(header).trim()] = index + 1);
  sheet.getRange(row, positions[STATUS_HEADER]).setValue(status);
  if (syncedAt) sheet.getRange(row, positions[SYNCED_AT_HEADER]).setValue(syncedAt);
  sheet.getRange(row, positions[DETAIL_HEADER]).setValue(detail);
}

function installVocTrigger() {
  const spreadsheet = SpreadsheetApp.getActive();
  ScriptApp.getProjectTriggers()
    .filter(trigger => trigger.getHandlerFunction() === 'onVocFormSubmit')
    .forEach(trigger => ScriptApp.deleteTrigger(trigger));
  ScriptApp.newTrigger('onVocFormSubmit')
    .forSpreadsheet(spreadsheet)
    .onFormSubmit()
    .create();
}

function testSelectedResponse() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const row = sheet.getActiveRange().getRow();
  if (row <= 1) throw new Error('Select a response row first.');
  onVocFormSubmit({range: sheet.getRange(row, 1)});
}

function testLatestResponse() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const row = sheet.getLastRow();
  if (row <= 1) throw new Error('No response row found.');
  onVocFormSubmit({range: sheet.getRange(row, 1)});
}

function retryFailedResponses() {
  const props = PropertiesService.getScriptProperties();
  let remaining = Number(props.getProperty('VOC_MAX_RETRY_ROWS') || 20);
  const spreadsheet = SpreadsheetApp.getActive();

  for (const sheet of spreadsheet.getSheets()) {
    if (remaining <= 0 || sheet.getLastRow() <= 1) break;
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
    const statusColumn = headers.findIndex(header => String(header).trim() === STATUS_HEADER) + 1;
    if (!statusColumn) continue;

    const statuses = sheet.getRange(2, statusColumn, sheet.getLastRow() - 1, 1).getDisplayValues();
    for (let index = 0; index < statuses.length && remaining > 0; index += 1) {
      if (String(statuses[index][0]).trim().toUpperCase() !== 'ERROR') continue;
      const row = index + 2;
      try {
        onVocFormSubmit({range: sheet.getRange(row, 1)});
      } catch (error) {
        console.error('VOC retry failed for row ' + row + ': ' + error);
      }
      remaining -= 1;
    }
  }
}

function installVocRetryTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(trigger => trigger.getHandlerFunction() === 'retryFailedResponses')
    .forEach(trigger => ScriptApp.deleteTrigger(trigger));
  ScriptApp.newTrigger('retryFailedResponses')
    .timeBased()
    .everyHours(6)
    .create();
}

function testCloudConnection() {
  const props = PropertiesService.getScriptProperties();
  const endpoint = props.getProperty('VOC_ENDPOINT');
  const serviceAccount = props.getProperty('VOC_INVOKER_SERVICE_ACCOUNT');
  const identityToken = getCloudRunIdentityToken(endpoint, serviceAccount);
  const response = UrlFetchApp.fetch(endpoint.replace(/\/$/, '') + '/health', {
    method: 'get',
    headers: {'Authorization': 'Bearer ' + identityToken},
    muteHttpExceptions: true
  });
  if (response.getResponseCode() !== 200) {
    throw new Error('Cloud connection failed: HTTP ' + response.getResponseCode() + ' ' + response.getContentText());
  }
  console.log(response.getContentText());
}
