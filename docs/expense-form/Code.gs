/****************************************************************************************
 * Ouja Residence — Field-Expense Form glue (Google Apps Script)
 * عوجا — ربط نموذج مصاريف الميدان بنظام عوجا و Hostaway
 *
 * WHAT THIS DOES / وش يسوي هذا الكود:
 *   1) onFormSubmit  → كل ما موظف يرسل النموذج، يدفع الصف لنظام عوجا (/api/expenses/ingest)
 *                      ثم يكتب الحالة (مُرحّل/بانتظار/فشل) رجوع في عمود "الحالة" بالشيت.
 *   2) syncDropdowns → يحدّث قوائم النموذج (الشقق + الأنواع + الفئات + الموظفين + طرق الدفع)
 *                      من نظام عوجا، فتظل الشقق مطابقة لـ Hostaway دائماً (المتطلب A.2).
 *
 * This script is bound to the RESPONSES SHEET (مرتبط بشيت الردود).
 * The form's File-upload (receipt) shows up in the sheet as a Google Drive LINK — we send
 * only that link, never the image bytes (Global rule #6).
 ****************************************************************************************/

/* ============================== CONFIG / الإعدادات ============================== */
// Base URL of the Ouja worker (no trailing slash). رابط نظام عوجا (بدون / في الآخر).
var BASE_URL = 'https://worker-production-5d63.up.railway.app';

// Same value you set on Railway as EXPENSE_INGEST_SECRET. نفس السر المحفوظ في Railway.
var INGEST_SECRET = 'PUT-YOUR-EXPENSE_INGEST_SECRET-HERE';

// The Google Form ID (from the form's edit URL: .../forms/d/<THIS-PART>/edit).
// معرّف النموذج (من رابط تعديل النموذج). يلزم لتحديث القوائم تلقائياً.
var FORM_ID = 'PUT-YOUR-GOOGLE-FORM-ID-HERE';

// Map each logical field to the EXACT question title in your Google Form.
// اربط كل حقل بعنوان السؤال في النموذج بالضبط (انسخه حرفياً).
var Q = {
  submitter:        'مين اللي يرسل؟',                 // Who is submitting?
  apartment:        'الشقة',                          // Apartment
  maintenance_type: 'نوع الصيانة',                    // Maintenance type
  category:         'فئة المصروف',                    // Expense category
  amount:           'المبلغ المدفوع (ر.س)',            // Amount paid (SAR)
  expense_date:     'تاريخ المصروف',                  // Date of the expense
  receipt:          'صورة الفاتورة',                  // Receipt photo (file upload)
  no_receipt_reason:'إذا ما فيه فاتورة، وش السبب؟',   // No-receipt reason (short text)
  vendor:           'المحل / المورّد (اختياري)',       // Vendor / shop (optional)
  payment_method:   'طريقة الدفع (اختياري)',          // Payment method (optional)
  note:             'ملاحظة (اختياري)'                // Note (optional)
};

// Name of the status column we write back into the responses sheet.
var STATUS_HEADER = 'الحالة (تلقائي)';   // "Status (auto)"

// Which dropdowns to keep in sync from the system. أي قوائم نحدّثها تلقائياً.
var SYNC = {
  apartment: true, maintenance_type: true, category: true,
  submitter: true, payment_method: true
};

/* ============================== INGEST / الإرسال للنظام ============================== */
function onFormSubmit(e) {
  try {
    var sheet = e.range.getSheet();
    var row = e.range.getRow();
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    var idx = {};
    for (var i = 0; i < headers.length; i++) idx[String(headers[i]).trim()] = i;

    var vals = e.values; // row values aligned to headers (incl. Timestamp at index 0)
    function cell(title) {
      var t = Q[title];
      if (t == null) return '';
      var c = idx[t];
      return (c == null || c >= vals.length) ? '' : vals[c];
    }

    var receiptLink = String(cell('receipt') || '').trim();
    var noReceipt   = String(cell('no_receipt_reason') || '').trim();

    var payload = {
      submission_id:     'gf-' + sheet.getSheetId() + '-' + row,   // idempotent per row
      submitter:         String(cell('submitter') || '').trim(),
      apartment:         String(cell('apartment') || '').trim(),
      maintenance_type:  String(cell('maintenance_type') || '').trim(),
      category:          String(cell('category') || '').trim(),
      amount:            String(cell('amount') || '').trim(),
      expense_date:      _fmtDate(cell('expense_date')),
      receipt_link:      receiptLink,
      no_receipt_reason: receiptLink ? '' : noReceipt,
      vendor:            String(cell('vendor') || '').trim(),
      payment_method:    String(cell('payment_method') || '').trim(),
      note:              String(cell('note') || '').trim(),
      submitted_at:      _fmtDateTime(vals[0])   // Timestamp column
    };

    var res = UrlFetchApp.fetch(BASE_URL + '/api/expenses/ingest?secret=' + encodeURIComponent(INGEST_SECRET), {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });

    var status = _statusFromResponse(res);
    _writeStatus(sheet, row, headers, status);
  } catch (err) {
    try { _writeStatus(e.range.getSheet(), e.range.getRow(),
      e.range.getSheet().getRange(1,1,1,e.range.getSheet().getLastColumn()).getValues()[0],
      'خطأ سكربت / Script error: ' + err); } catch (e2) {}
  }
}

function _statusFromResponse(res) {
  var code = res.getResponseCode();
  if (code < 200 || code >= 300) return 'فشل الإرسال / Send failed (HTTP ' + code + ')';
  var j; try { j = JSON.parse(res.getContentText()); } catch (e) { return 'تم الإرسال / Sent'; }
  var r = (j.results && j.results[0]) || {};
  var map = {
    posted:    '✅ مُرحّل لـHostaway / Posted',
    ready:     '✅ جاهز / Ready',
    held:      '⏳ بانتظار المراجعة / On hold' + (r.primary_reason ? ' (' + r.primary_reason + ')' : ''),
    failed:    '⚠ فشل الترحيل / Failed' + (r.primary_reason ? ' (' + r.primary_reason + ')' : ''),
    captured:  'تم الاستلام / Captured'
  };
  var s = map[r.status] || ('تم / OK (' + (r.status || '') + ')');
  if (r.ref) s = r.ref + ' · ' + s;
  return s;
}

function _writeStatus(sheet, row, headers, text) {
  var c = -1;
  for (var i = 0; i < headers.length; i++) if (String(headers[i]).trim() === STATUS_HEADER) { c = i; break; }
  if (c === -1) { // create the status column if it doesn't exist
    c = headers.length;
    sheet.getRange(1, c + 1).setValue(STATUS_HEADER);
  }
  sheet.getRange(row, c + 1).setValue(text);
}

function _fmtDate(v) {
  if (v == null || v === '') return '';
  var d = (v instanceof Date) ? v : new Date(v);
  if (isNaN(d.getTime())) return String(v).slice(0, 10);
  return Utilities.formatDate(d, 'Asia/Riyadh', 'yyyy-MM-dd');
}
function _fmtDateTime(v) {
  if (v == null || v === '') return '';
  var d = (v instanceof Date) ? v : new Date(v);
  if (isNaN(d.getTime())) return String(v);
  return Utilities.formatDate(d, 'Asia/Riyadh', "yyyy-MM-dd'T'HH:mm:ss");
}

/* ============================== DROPDOWN SYNC / تحديث القوائم ============================== */
// Run on a time trigger (e.g. hourly) AND can be run manually from the editor.
function syncDropdowns() {
  var res = UrlFetchApp.fetch(BASE_URL + '/api/expenses/options?key=' + encodeURIComponent(INGEST_SECRET), {
    method: 'get', muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 200) {
    throw new Error('options HTTP ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 200));
  }
  var o = JSON.parse(res.getContentText());
  var apartments = (o.apartments || []).map(function (a) { return a.name; });

  var form = FormApp.openById(FORM_ID);
  if (SYNC.apartment)        _setChoices(form, Q.apartment, apartments);
  if (SYNC.maintenance_type) _setChoices(form, Q.maintenance_type, o.maintenance_types || []);
  if (SYNC.category)         _setChoices(form, Q.category, o.categories || []);
  if (SYNC.submitter)        _setChoices(form, Q.submitter, o.employees || []);
  if (SYNC.payment_method)   _setChoices(form, Q.payment_method, o.payment_methods || []);
}

function _setChoices(form, title, values) {
  values = (values || []).filter(function (v) { return String(v || '').trim() !== ''; });
  if (!values.length) return;
  var items = form.getItems();
  for (var i = 0; i < items.length; i++) {
    if (String(items[i].getTitle()).trim() !== String(title).trim()) continue;
    var type = items[i].getType();
    if (type === FormApp.ItemType.LIST)            { items[i].asListItem().setChoiceValues(values); return; }
    if (type === FormApp.ItemType.MULTIPLE_CHOICE) { items[i].asMultipleChoiceItem().setChoiceValues(values); return; }
    return; // found the question but it's not a choice type — leave it alone
  }
}

/* ============================== ONE-TIME SETUP HELPERS ============================== */
// Run ONCE from the editor to install the triggers. شغّلها مرة وحدة لتركيب المشغّلات.
function installTriggers() {
  var ss = SpreadsheetApp.getActive();
  // remove old copies first / احذف القديمة
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'onFormSubmit' || t.getHandlerFunction() === 'syncDropdowns') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('onFormSubmit').forSpreadsheet(ss).onFormSubmit().create();
  ScriptApp.newTrigger('syncDropdowns').timeBased().everyHours(1).create();
  syncDropdowns(); // do a first sync now
}
