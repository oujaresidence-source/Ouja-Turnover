"""Secure, data-free shell for monthly-rental operations."""

from __future__ import annotations


ASSET_VERSION = "v20260825b"
CSS_PATH = "/monthly/static/monthly_ops.%s.css" % ASSET_VERSION
JS_PATH = "/monthly/static/monthly_ops.%s.js" % ASSET_VERSION


def render_monthly_ops_page() -> str:
    """Render only static staff UI; operational data comes from gated APIs."""

    return """<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#173d32">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>تشغيل السكن الشهري · عوجا</title>
  <link rel="stylesheet" href="%s">
  <script src="%s" defer></script>
</head>
<body>
  <a class="skip-link" href="#monthly-ops-main" data-copy="skipLink">انتقل إلى المحتوى</a>
  <div class="ops-shell">
    <header class="ops-header">
      <div class="ops-brand" aria-label="عوجا، تشغيل السكن الشهري" data-copy-aria="brandLabel">
        <span class="ops-brand-mark" aria-hidden="true">عوجا</span>
        <span data-copy="productName">تشغيل السكن الشهري</span>
      </div>
      <nav class="ops-nav" aria-label="روابط الصفحة" data-copy-aria="pageNav">
        <a id="monthly-catalog-link" href="/monthly/ops/listings" data-copy="listingData">بيانات الشقق</a>
        <a id="ops-dashboard-link" href="/dashboard" data-copy="backDashboard">العودة للوحة عوجا</a>
        <button id="ops-language" type="button" aria-label="Switch to English">English</button>
      </nav>
    </header>

    <main id="monthly-ops-main" class="ops-main" tabindex="-1">
      <section id="launch-panel" class="launch-panel" aria-labelledby="launch-title" aria-busy="true">
        <div>
          <p class="section-label" data-copy="readinessLabel">قرار الإطلاق</p>
          <h1 id="launch-title" data-copy="loadingTitle">جاري فحص جاهزية السكن الشهري</h1>
          <p id="launch-detail" class="launch-detail" data-copy="loadingDetail">نراجع النشر، الأسعار، التوفر، والتحويل إلى فريق عوجا.</p>
        </div>
        <div class="refresh-control">
          <span id="checked-at" class="time-note" data-copy="notChecked">لم يكتمل الفحص بعد</span>
          <button id="refresh-ops" class="button button-secondary" type="button" data-copy="refresh">تحديث الحالة</button>
        </div>
      </section>

      <section id="loading-state" class="loading-state" aria-label="جاري تحميل بيانات التشغيل" data-copy-aria="loadingLabel">
        <span></span><span></span><span></span><span></span>
      </section>
      <section id="ops-error" class="state-panel state-error" role="alert" hidden>
        <h2 id="ops-error-title">تعذر تحميل بيانات التشغيل</h2>
        <p id="ops-error-detail">حاول تحديث الصفحة.</p>
      </section>

      <div id="ops-content" hidden>
        <section class="ops-section" aria-labelledby="inventory-title">
          <div class="section-heading">
            <div>
              <h2 id="inventory-title" data-copy="inventoryTitle">أهلية النشر والتغطية</h2>
              <p data-copy="inventoryDetail">الأرقام تحسب من المخزون المستلم نفسه، بدون مضاعفة أو تقدير.</p>
            </div>
            <div id="source-refreshes" class="source-refreshes" aria-live="polite">
              <span id="last-refresh" class="time-note"></span>
              <span id="calendar-refresh" class="time-note"></span>
              <span id="engine-refresh" class="time-note"></span>
            </div>
          </div>
          <dl id="inventory-counts" class="metric-band"></dl>
          <div id="coverage-list" class="coverage-list"></div>
        </section>

        <section class="ops-section" aria-labelledby="configuration-title">
          <div class="section-heading">
            <div>
              <h2 id="configuration-title" data-copy="configurationTitle">إعدادات التحويل والاستمرارية</h2>
              <p data-copy="configurationDetail">أي إعداد ناقص يظهر كمانع إطلاق، ولا يختفي خلف حالة عامة.</p>
            </div>
          </div>
          <dl id="configuration-list" class="status-list"></dl>
        </section>

        <section class="ops-section blocker-section" aria-labelledby="blockers-title">
          <div class="section-heading">
            <div>
              <h2 id="blockers-title" data-copy="blockersTitle">موانع الإطلاق الحمراء</h2>
              <p data-copy="blockersDetail">كل سبب يظهر برمزه ورقم الوحدة عند توفره.</p>
            </div>
            <span id="blocker-count" class="count-chip"></span>
          </div>
          <div id="blockers-list" class="issue-list"></div>
        </section>

        <div class="detail-columns">
          <section class="ops-section" aria-labelledby="content-title">
            <div class="section-heading">
              <div>
                <h2 id="content-title" data-copy="contentTitle">تعارضات المحتوى</h2>
                <p data-copy="contentDetail">العنوان، الغرف، اللغة، المرافق، وبيانات النشر.</p>
              </div>
            </div>
            <div id="content-conflicts" class="issue-list compact"></div>
          </section>
          <section class="ops-section" aria-labelledby="licence-title">
            <div class="section-heading">
              <div>
                <h2 id="licence-title" data-copy="licenceTitle">حالة معلومات الإعلان</h2>
                <p data-copy="licenceDetail">المفقود، المنتهي، والقريب من الانتهاء.</p>
              </div>
            </div>
            <div id="licence-expiry" class="issue-list compact"></div>
          </section>
        </div>

        <section class="ops-section" aria-labelledby="funnel-title">
          <div class="section-heading">
            <div>
              <h2 id="funnel-title" data-copy="funnelTitle">مسار الطلب الشهري</h2>
              <p data-copy="funnelDetail">من دخول الموقع إلى رد الفريق والنتيجة النهائية، بدون محتوى محادثات أو بيانات شخصية.</p>
            </div>
          </div>
          <dl id="lead-counts" class="metric-band compact-metrics"></dl>
          <div class="table-scroll" tabindex="0" aria-label="مراحل مسار الطلب" data-copy-aria="stagesTableLabel">
            <table>
              <caption data-copy="stagesCaption">عدد الجلسات أو الطلبات في كل مرحلة</caption>
              <thead><tr><th scope="col" data-copy="stage">المرحلة</th><th scope="col" data-copy="count">العدد</th></tr></thead>
              <tbody id="funnel-stages"></tbody>
            </table>
          </div>
          <div class="funnel-detail-grid">
            <section aria-labelledby="conversion-title">
              <h3 id="conversion-title" data-copy="conversionTitle">التحويل وسرعة الرد</h3>
              <dl id="conversion-list" class="status-list"></dl>
            </section>
            <section aria-labelledby="demand-title">
              <h3 id="demand-title" data-copy="demandTitle">الطلب المسجل</h3>
              <div id="demand-list" class="demand-groups"></div>
            </section>
          </div>
        </section>

        <section class="ops-section outcome-section" aria-labelledby="outcome-title">
          <div class="section-heading">
            <div>
              <h2 id="outcome-title" data-copy="outcomeTitle">مساحة متابعة الطلب</h2>
              <p data-copy="outcomeDetail">ابحث بالمرجع الكامل قبل تسجيل أي إجراء. لا تُرسل هذه الصفحة رسائل للعملاء.</p>
            </div>
          </div>

          <form id="lead-lookup-form" class="lookup-form" autocomplete="off" novalidate>
            <label>
              <span data-copy="leadReference">مرجع الطلب</span>
              <input name="lead_reference" id="lead-reference" required maxlength="64" inputmode="text" spellcheck="false" placeholder="OJM-YYYYMMDD-XXXX" aria-describedby="lead-reference-error">
              <span id="lead-reference-error" class="field-error" role="alert"></span>
            </label>
            <button id="lead-lookup" class="button button-secondary" type="submit" data-copy="lookupLead">عرض الطلب</button>
            <span id="lookup-status" role="status" aria-live="polite"></span>
          </form>

          <div id="lead-workspace" hidden>
            <div class="lead-workspace-grid">
              <section id="lead-detail" class="lead-panel" aria-labelledby="lead-detail-title">
                <h3 id="lead-detail-title" data-copy="leadDetailTitle">ملخص الطلب المحفوظ</h3>
                <dl id="lead-detail-list" class="lead-detail-list"></dl>
              </section>
              <section id="lead-journey" class="lead-panel" aria-labelledby="lead-journey-title">
                <h3 id="lead-journey-title" data-copy="leadJourneyTitle">رحلة العميل المسجلة</h3>
                <ol id="lead-journey-list" class="journey-list"></ol>
              </section>
              <section id="lead-actions" class="lead-panel" aria-labelledby="lead-actions-title">
                <h3 id="lead-actions-title" data-copy="leadActionsTitle">إجراءات الفريق السابقة</h3>
                <ol id="lead-actions-list" class="journey-list"></ol>
              </section>
            </div>

            <form id="staff-action-form" class="workflow-form" autocomplete="off" novalidate>
              <fieldset>
                <legend data-copy="staffActionTitle">إجراء متابعة آمن</legend>
                <p class="form-help" data-copy="staffActionDetail">يسجل الإجراء داخليًا فقط ولا يرسل رسالة أو يفتح واتساب.</p>
                <div class="form-grid">
                  <label>
                    <span data-copy="staffActionLabel">الإجراء</span>
                    <select name="staff_action" id="staff-action" required aria-describedby="staff-action-error" disabled>
                      <option value="confirm_request" data-copy="confirm_request">تأكيد مراجعة الطلب</option>
                      <option value="request_information" data-copy="request_information">طلب معلومات ناقصة</option>
                      <option value="prepare_alternative" data-copy="prepare_alternative">تجهيز بديل</option>
                    </select>
                    <span id="staff-action-error" class="field-error" role="alert"></span>
                  </label>
                  <label id="information-reason-field" hidden>
                    <span data-copy="informationReason">المعلومة المطلوبة</span>
                    <select name="information_reason" id="information-reason" aria-describedby="information-reason-error" disabled></select>
                    <span id="information-reason-error" class="field-error" role="alert"></span>
                  </label>
                  <label id="alternative-reason-field" hidden>
                    <span data-copy="alternativeReason">سبب تجهيز البديل</span>
                    <select name="alternative_reason" id="alternative-reason" aria-describedby="alternative-reason-error" disabled></select>
                    <span id="alternative-reason-error" class="field-error" role="alert"></span>
                  </label>
                  <label id="alternative-listing-field" hidden>
                    <span data-copy="alternativeListing">رقم الوحدة البديلة المنشورة</span>
                    <input name="alternative_listing_id" id="alternative-listing-id" maxlength="80" spellcheck="false" aria-describedby="alternative-listing-error" disabled>
                    <span id="alternative-listing-error" class="field-error" role="alert"></span>
                  </label>
                </div>
                <div class="form-actions">
                  <button id="submit-staff-action" class="button button-primary" type="submit" data-copy="recordAction" disabled>تسجيل الإجراء</button>
                  <span id="staff-action-status" role="status" aria-live="polite"></span>
                </div>
              </fieldset>
            </form>

            <section id="prepared-alternative" class="prepared-alternative" aria-labelledby="prepared-title" hidden>
              <h3 id="prepared-title" data-copy="preparedTitle">ملخص البديل المجهز</h3>
              <p id="prepared-alternative-copy"></p>
              <button id="copy-alternative" class="button button-secondary" type="button" data-copy="copyAlternative">نسخ الملخص</button>
              <span id="copy-status" role="status" aria-live="polite"></span>
            </section>

            <form id="lead-outcome-form" class="workflow-form" autocomplete="off" novalidate>
              <fieldset>
                <legend data-copy="outcomeUpdateTitle">تسجيل رد أو نتيجة نهائية</legend>
            <div class="form-grid">
              <label>
                <span data-copy="actionLabel">التحديث المطلوب</span>
                <select name="outcome" id="lead-action" required disabled>
                  <option value="response" data-copy="actionResponse">تسجيل رد الفريق</option>
                  <option value="booked" data-copy="actionBooked">تسجيل الحجز</option>
                  <option value="lost" data-copy="actionLost">تسجيل خسارة الطلب</option>
                </select>
              </label>
              <label id="discount-field">
                <span data-copy="discountClassification">هل طلب العميل تخفيض السعر؟</span>
                <select name="discount_requested" id="discount-requested" disabled>
                  <option value="unknown" data-copy="unknown">غير مصنف</option>
                  <option value="yes" data-copy="yes">نعم</option>
                  <option value="no" data-copy="no">لا</option>
                </select>
              </label>
              <label id="lost-reason-field" hidden>
                <span data-copy="lostReason">سبب خسارة الطلب</span>
                <select name="lost_reason" id="lost-reason" aria-describedby="lost-reason-error" disabled>
                  <option value="" data-copy="chooseReason">اختر سببًا</option>
                </select>
                <span id="lost-reason-error" class="field-error" role="alert"></span>
              </label>
            </div>
            <div class="form-actions">
              <button id="submit-outcome" class="button button-primary" type="submit" data-copy="recordUpdate" disabled>تسجيل التحديث</button>
              <span id="form-status" role="status" aria-live="polite"></span>
            </div>
              </fieldset>
          </form>
          </div>
        </section>
      </div>
    </main>
  </div>
</body>
</html>""" % (CSS_PATH, JS_PATH)


__all__ = ["ASSET_VERSION", "CSS_PATH", "JS_PATH", "render_monthly_ops_page"]
