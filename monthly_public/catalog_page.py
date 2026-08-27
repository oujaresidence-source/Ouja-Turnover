"""Static, authenticated shell for monthly apartment readiness."""

from __future__ import annotations

from .fonts import FONT_CSS_PATH

ASSET_VERSION = "v20260828a"
CSS_PATH = "/monthly/static/monthly_catalog.%s.css" % ASSET_VERSION
JS_PATH = "/monthly/static/monthly_catalog.%s.js" % ASSET_VERSION


def render_monthly_catalog_page() -> str:
    """Render a data-free page; every apartment value comes from gated APIs."""

    return """<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#173d32">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>بيانات شقق السكن الشهري · عوجا</title>
  <link rel="stylesheet" href="%s">
  <link rel="stylesheet" href="%s">
  <script src="%s" defer></script>
</head>
<body>
  <a class="skip-link" href="#catalog-main" data-copy="skipLink">انتقل إلى المحتوى</a>
  <div class="catalog-shell">
    <header class="catalog-header">
      <a class="catalog-brand" id="catalog-ops-link" href="/monthly/ops" aria-label="عوجا، تشغيل السكن الشهري">
        <span class="catalog-brand-mark" aria-hidden="true">عوجا</span>
        <span data-copy="productName">بيانات الشقق</span>
      </a>
      <nav class="catalog-nav" aria-label="روابط الصفحة">
        <a id="catalog-dashboard-link" href="/dashboard" data-copy="dashboard">لوحة عوجا</a>
        <button id="catalog-language" type="button" aria-label="Switch to English">English</button>
      </nav>
    </header>

    <main id="catalog-main" class="catalog-main" tabindex="-1">
      <header class="page-heading">
        <div>
          <p class="context-label" data-copy="contextLabel">السكن الشهري</p>
          <h1 data-copy="pageTitle">جهّز كل شقة للنشر من مكان واحد</h1>
          <p data-copy="pageDetail">راجع البيانات المعبأة تلقائيًا، أكمل الناقص، ثم اعتمدها للموقع.</p>
        </div>
        <div class="page-heading-actions">
          <p data-copy="previewCustomerDetail">يعرض كل الشقق داخليًا ولا ينشر أي شقة</p>
          <a id="preview-customer-journey" class="button button-primary" href="/monthly/ops/preview" data-copy="previewCustomerJourney">معاينة رحلة العميل</a>
          <button id="refresh-catalog" class="button button-secondary" type="button" data-copy="refreshData">تحديث البيانات</button>
        </div>
      </header>

      <section id="catalog-summary" class="catalog-summary" aria-live="polite" aria-busy="true">
        <div class="summary-skeleton" aria-label="جاري تحميل حالة الشقق">
          <span></span><span></span><span></span><span></span>
        </div>
      </section>

      <nav class="workspace-tabs" aria-label="أقسام تجهيز البيانات" role="tablist">
        <button id="tab-portfolio" class="workspace-tab active" type="button" role="tab" aria-selected="true" aria-controls="portfolio" data-panel="portfolio" data-copy="apartmentsTab">الشقق</button>
        <button id="tab-showcases" class="workspace-tab" type="button" role="tab" aria-selected="false" aria-controls="showcases" data-panel="showcases" data-copy="showcasesTab">العروض الخاصة</button>
        <button id="tab-global" class="workspace-tab" type="button" role="tab" aria-selected="false" aria-controls="global-setup" data-panel="global-setup" data-copy="settingsTab">الإعدادات المشتركة</button>
        <button id="tab-places" class="workspace-tab" type="button" role="tab" aria-selected="false" aria-controls="places" data-panel="places" data-copy="placesTab">الأماكن المعتمدة</button>
      </nav>

      <section id="catalog-error" class="state-panel state-error" role="alert" hidden>
        <h2 data-copy="loadFailed">تعذر تحميل بيانات الشقق</h2>
        <p id="catalog-error-detail" data-copy="loadFailedDetail">حاول التحديث، ولن تتأثر البيانات المعتمدة الحالية.</p>
      </section>

      <section id="global-setup" class="workspace-panel" role="tabpanel" aria-labelledby="tab-global" hidden>
        <div class="section-heading">
          <div>
            <h2 id="global-title" data-copy="globalTitle">إعدادات تُكتب مرة واحدة</h2>
            <p data-copy="globalDetail">رقم التواصل، أوقات الرد، التأمين، طرق الدفع، ومسار الإقامات من أربعة إلى ستة أشهر.</p>
          </div>
          <span id="settings-status" class="status-text" role="status" aria-live="polite"></span>
        </div>
        <form id="global-form" autocomplete="off" novalidate>
          <div id="global-fields" class="form-surface"></div>
          <div class="form-actions">
            <button id="save-settings" class="button button-secondary" type="submit" data-copy="saveDraft">حفظ المسودة</button>
            <button id="approve-settings" class="button button-primary" type="button" data-copy="approveSettings">اعتماد الإعدادات</button>
          </div>
        </form>
      </section>

      <section id="portfolio" class="workspace-panel" role="tabpanel" aria-labelledby="portfolio-title" aria-describedby="tab-portfolio">
        <div class="section-heading">
          <div>
            <h2 id="portfolio-title" data-copy="portfolioTitle">الشقق المستلمة</h2>
            <p data-copy="portfolioDetail">صف واحد لكل شقة فعلية، مع الناقص والخطوة التالية.</p>
          </div>
          <span id="portfolio-count" class="status-text" aria-live="polite"></span>
        </div>
        <form id="portfolio-filters" class="filter-bar" role="search" autocomplete="off">
          <label class="search-field">
            <span data-copy="searchLabel">ابحث برقم الشقة أو الاسم</span>
            <input id="listing-search" name="search" type="search" inputmode="search" autocomplete="off" data-copy-placeholder="searchPlaceholder" placeholder="مثال: 101 أو الملقا">
          </label>
          <label>
            <span data-copy="statusLabel">الحالة</span>
            <select id="status-filter" name="status">
              <option value="all" data-copy="allStatuses">كل الحالات</option>
              <option value="needs_review" data-copy="needsReview">تحتاج مراجعة</option>
              <option value="ready_for_approval" data-copy="readyApproval">جاهزة للاعتماد</option>
              <option value="published" data-copy="published">منشورة</option>
              <option value="source_blocked" data-copy="sourceBlocked">محجوبة من مصدر حي</option>
            </select>
          </label>
          <label>
            <span data-copy="blockerLabel">الناقص</span>
            <select id="blocker-filter" name="blocker">
              <option value="all" data-copy="allBlockers">كل الأسباب</option>
              <option value="licence" data-copy="licence">معلومات الإعلان</option>
              <option value="price" data-copy="price">السعر الرسمي</option>
              <option value="calendar" data-copy="calendar">التقويم</option>
              <option value="content" data-copy="content">المحتوى</option>
            </select>
          </label>
        </form>
        <div id="listing-table" class="listing-table" aria-live="polite"></div>
      </section>

      <section id="showcases" class="workspace-panel" role="tabpanel" aria-labelledby="tab-showcases" hidden>
        <div class="section-heading">
          <div>
            <h2 data-copy="showcasesTitle">روابط خاصة لمجموعة شقق</h2>
            <p data-copy="showcasesDetail">اجمع شقق المبنى في رابط دائم، واختر الغلاف والسعر لكل شقة بشكل مستقل.</p>
          </div>
          <button id="new-showcase" class="button button-secondary" type="button" data-copy="newShowcase">مجموعة جديدة</button>
        </div>
        <div class="showcase-workspace">
          <div id="showcase-list" class="showcase-list" aria-live="polite"></div>
          <form id="showcase-form" class="form-surface showcase-form" autocomplete="off" novalidate hidden>
            <div id="showcase-error" class="error-summary" role="alert" tabindex="-1" hidden></div>
            <div id="showcase-fields" class="form-grid"></div>
            <fieldset class="showcase-members span-all">
              <legend data-copy="showcaseApartments">شقق المجموعة</legend>
              <label class="search-field">
                <span data-copy="showcaseSearch">ابحث عن شقة</span>
                <input id="showcase-search" type="search" autocomplete="off" data-copy-placeholder="searchPlaceholder" placeholder="مثال: 101 أو الملقا">
              </label>
              <p data-copy="showcaseApartmentHelp">اختر كل الشقق الفعلية في المبنى. المعاينة الداخلية تعرضها كلها، والرابط العام يظهر الجاهز للنشر فقط.</p>
              <div id="showcase-listings" class="showcase-listings"></div>
            </fieldset>
            <div id="showcase-public-link" class="showcase-public-link" hidden></div>
            <footer class="form-actions showcase-actions">
              <span id="showcase-status" class="status-text" role="status" aria-live="polite"></span>
              <button id="save-showcase" class="button button-secondary" type="submit" data-copy="saveDraft">حفظ المسودة</button>
              <button id="approve-showcase" class="button button-primary" type="button" data-copy="approveShowcase">اعتماد الرابط</button>
            </footer>
          </form>
        </div>
      </section>

      <section id="survey" class="workspace-panel survey-panel" role="region" aria-labelledby="survey-title" hidden>
        <header class="survey-header">
          <button id="close-survey" class="back-button" type="button" data-copy="backToApartments">العودة للشقق</button>
          <div>
            <p id="survey-source-title" class="context-label"></p>
            <h2 id="survey-title" data-copy="surveyTitle">مراجعة الشقة</h2>
            <p id="survey-meta" class="survey-meta"></p>
          </div>
          <div id="survey-completion" class="completion-meter" aria-label="نسبة اكتمال البيانات"></div>
        </header>
        <div class="survey-layout">
          <nav id="survey-progress" class="survey-progress" aria-label="أقسام مراجعة الشقة"></nav>
          <form id="survey-form" class="survey-form" autocomplete="off" novalidate>
            <div id="survey-error-summary" class="error-summary" role="alert" tabindex="-1" hidden></div>
            <div id="survey-sections"></div>
            <footer class="survey-actions">
              <span id="survey-save-status" class="status-text" role="status" aria-live="polite"></span>
              <div>
                <button id="save-profile" class="button button-secondary" type="submit" data-copy="saveDraft">حفظ المسودة</button>
                <button id="preview-profile" class="button button-secondary" type="button" data-copy="saveAndPreview">حفظ ومشاهدة كتجربة عميل</button>
                <button id="approve-profile" class="button button-primary" type="button" data-copy="approveAndRefresh">اعتماد وتحديث الموقع</button>
              </div>
            </footer>
          </form>
        </div>
      </section>

      <section id="places" class="workspace-panel" role="tabpanel" aria-labelledby="tab-places" hidden>
        <div class="section-heading">
          <div>
            <h2 id="places-title" data-copy="placesTitle">الأماكن المهمة للعملاء</h2>
            <p data-copy="placesDetail">أدخل المكان مرة واحدة، ولا يظهر القرب إلا بعد اعتماد إحداثيات الطرفين.</p>
          </div>
          <button id="new-place" class="button button-secondary" type="button" data-copy="addPlace">إضافة مكان</button>
        </div>
        <div id="places-summary" class="places-summary" aria-live="polite"></div>
        <div class="places-layout">
          <div id="places-list" class="places-list" aria-live="polite"></div>
          <form id="place-form" class="form-surface" autocomplete="off" novalidate hidden>
            <div id="place-fields"></div>
            <div class="form-actions">
              <button id="save-place" class="button button-secondary" type="submit" data-copy="saveDraft">حفظ المسودة</button>
              <button id="approve-place" class="button button-primary" type="button" data-copy="approvePlace">اعتماد المكان</button>
            </div>
          </form>
        </div>
      </section>
    </main>
  </div>
</body>
</html>""" % (FONT_CSS_PATH, CSS_PATH, JS_PATH)


__all__ = ["ASSET_VERSION", "CSS_PATH", "JS_PATH", "render_monthly_catalog_page"]
