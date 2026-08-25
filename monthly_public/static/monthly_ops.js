(function () {
  "use strict";

  const API = {
    health: "/api/monthly/ops/health",
    funnel: "/api/monthly/ops/funnel",
    lead: "/api/monthly/ops/lead",
    action: "/api/monthly/ops/action",
    response: "/api/monthly/ops/response",
    outcome: "/api/monthly/ops/outcome"
  };
  const STAGES = [
    "landing_view", "entry_route_choice", "matcher_start", "matcher_answer",
    "matcher_completion", "results_view", "result_impression", "listing_view",
    "whatsapp_click", "lead_created", "team_response", "booked", "lost"
  ];
  const LOST_REASONS = [
    "price", "unavailable_dates", "location", "space", "contract_terms",
    "no_response", "booked_elsewhere", "other"
  ];
  const PURPOSES = ["work", "family", "treatment", "visit"];
  const DURATION_BANDS = ["1_month", "2_3_months", "4_6_months"];
  const INFORMATION_REASONS = ["dates", "residents", "place", "contract_terms", "other"];
  const ALTERNATIVE_REASONS = ["lower_price", "dates", "location", "space", "contract_terms"];
  const STAFF_ACTIONS = ["confirm_request", "request_information", "prepare_alternative"];
  const REFERENCE = /^[A-Z0-9][A-Z0-9-]{5,63}$/;

  const COPY = {
    ar: {
      pageTitle: "تشغيل السكن الشهري · عوجا",
      skipLink: "انتقل إلى المحتوى",
      brandLabel: "عوجا، تشغيل السكن الشهري",
      loadingLabel: "جاري تحميل بيانات التشغيل",
      productName: "تشغيل السكن الشهري",
      pageNav: "روابط الصفحة",
      backDashboard: "العودة للوحة عوجا",
      readinessLabel: "قرار الإطلاق",
      loadingTitle: "جاري فحص جاهزية السكن الشهري",
      loadingDetail: "نراجع النشر، الأسعار، التوفر، والتحويل إلى فريق عوجا.",
      notChecked: "لم يكتمل الفحص بعد",
      refresh: "تحديث الحالة",
      refreshing: "جاري التحديث",
      launchReady: "جاهز للإطلاق من ناحية التشغيل",
      launchBlocked: "الإطلاق متوقف حتى معالجة الموانع",
      readyDetail: "كل فحوص النشر والتواصل والتخزين المطلوبة سليمة.",
      blockedDetail: "يوجد {count} مانع إطلاق أحمر يحتاج إجراءً واضحًا.",
      inventoryTitle: "أهلية النشر والتغطية",
      inventoryDetail: "الأرقام تحسب من المخزون المستلم نفسه، بدون مضاعفة أو تقدير.",
      configurationTitle: "إعدادات التحويل والاستمرارية",
      configurationDetail: "أي إعداد ناقص يظهر كمانع إطلاق، ولا يختفي خلف حالة عامة.",
      blockersTitle: "موانع الإطلاق الحمراء",
      blockersDetail: "كل سبب يظهر برمزه ورقم الوحدة عند توفره.",
      contentTitle: "تعارضات المحتوى",
      contentDetail: "العنوان، الغرف، اللغة، المرافق، وبيانات النشر.",
      licenceTitle: "حالة معلومات الإعلان",
      licenceDetail: "المفقود، المنتهي، والقريب من الانتهاء.",
      funnelTitle: "مسار الطلب الشهري",
      funnelDetail: "من دخول الموقع إلى رد الفريق والنتيجة النهائية، بدون محتوى محادثات أو بيانات شخصية.",
      stagesTableLabel: "مراحل مسار الطلب",
      stagesCaption: "عدد الجلسات أو الطلبات في كل مرحلة",
      stage: "المرحلة",
      count: "العدد",
      conversionTitle: "التحويل وسرعة الرد",
      demandTitle: "الطلب المسجل",
      outcomeTitle: "مساحة متابعة الطلب",
      outcomeDetail: "ابحث بالمرجع الكامل قبل تسجيل أي إجراء. لا تُرسل هذه الصفحة رسائل للعملاء.",
      leadReference: "مرجع الطلب",
      lookupLead: "عرض الطلب",
      lookingUp: "جاري جلب الطلب",
      lookupFound: "تم تحميل الطلب. الإجراءات متاحة الآن.",
      leadDetailTitle: "ملخص الطلب المحفوظ",
      leadJourneyTitle: "رحلة العميل المسجلة",
      leadActionsTitle: "إجراءات الفريق السابقة",
      noHomeSelected: "لم يحدد العميل بيتًا لهذا الطلب.",
      listingLabel: "الوحدة المختارة",
      titleLabel: "البيت",
      purposeLabel: "غرض الإقامة",
      datesLabel: "التواريخ",
      durationLabel: "المدة",
      residentsLabel: "عدد السكان",
      placeLabel: "معرف المكان",
      quoteLabel: "السعر الرسمي المحفوظ",
      includedLabel: "المشمول",
      utilitiesLabel: "الخدمات المتغيرة",
      cleaningLabel: "التنظيف",
      depositLabel: "التأمين والاسترداد",
      paymentMethodsLabel: "طرق الدفع",
      internetTerm: "الإنترنت",
      maintenanceTerm: "الصيانة",
      createdAt: "تاريخ إنشاء الطلب",
      respondedAt: "أول رد للفريق",
      outcomeLabel: "النتيجة",
      notRecorded: "غير مسجل",
      emptyJourney: "لا توجد مراحل رحلة معتمدة لهذا الطلب.",
      emptyActions: "لا توجد إجراءات فريق مسجلة.",
      rankLabel: "الترتيب {value}",
      entry_guided: "مساعدة بالاختيار",
      entry_browse: "تصفح كل البيوت",
      monthsLabel: "{value} شهر",
      staffActionTitle: "إجراء متابعة آمن",
      staffActionDetail: "يسجل الإجراء داخليًا فقط ولا يرسل رسالة أو يفتح واتساب.",
      staffActionLabel: "الإجراء",
      confirm_request: "تأكيد مراجعة الطلب",
      request_information: "طلب معلومات ناقصة",
      prepare_alternative: "تجهيز بديل",
      informationReason: "المعلومة المطلوبة",
      alternativeReason: "سبب تجهيز البديل",
      alternativeListing: "رقم الوحدة البديلة المنشورة",
      recordAction: "تسجيل الإجراء",
      info_dates: "تأكيد التواريخ",
      info_residents: "تأكيد عدد السكان",
      info_place: "تأكيد المكان المطلوب",
      info_contract_terms: "تأكيد شروط العقد المطلوبة",
      info_other: "معلومة أخرى",
      alternative_lower_price: "سعر أقل",
      alternative_dates: "توفر التواريخ",
      alternative_location: "موقع أنسب",
      alternative_space: "مساحة أنسب",
      alternative_contract_terms: "شروط العقد",
      chooseInformationReason: "اختر المعلومة المطلوبة",
      chooseAlternativeReason: "اختر سبب تجهيز البديل",
      invalidInformationReason: "اختر نوع المعلومة المطلوبة.",
      invalidAlternativeReason: "اختر سبب تجهيز البديل.",
      invalidAlternativeListing: "أدخل رقم وحدة منشورة صحيحًا.",
      actionSaved: "تم تسجيل الإجراء وتحديث الطلب والتقارير.",
      preparedTitle: "ملخص البديل المجهز",
      copyAlternative: "نسخ الملخص",
      copied: "تم نسخ الملخص. لم تُرسل أي رسالة.",
      copyFailed: "تعذر النسخ. حدد النص وانسخه يدويًا.",
      outcomeUpdateTitle: "تسجيل رد أو نتيجة نهائية",
      actionLabel: "التحديث المطلوب",
      actionResponse: "تسجيل رد الفريق",
      actionBooked: "تسجيل الحجز",
      actionLost: "تسجيل خسارة الطلب",
      discountClassification: "هل طلب العميل تخفيض السعر؟",
      unknown: "غير مصنف",
      yes: "نعم",
      no: "لا",
      lostReason: "سبب خسارة الطلب",
      chooseReason: "اختر سببًا",
      recordUpdate: "تسجيل التحديث",
      received: "مستلمة",
      valid: "صالحة للفحص",
      blocked: "محجوبة",
      published: "منشورة",
      calendar: "تغطية التقويم",
      price: "تغطية السعر الرسمي",
      coverageOf: "{covered} من {total}",
      noInventory: "لا يوجد مخزون مستلم لحساب النسبة.",
      missingIds: "مفقود: {ids}",
      staleIds: "قديم: {ids}",
      noCoverageGaps: "لا توجد فجوات مسجلة.",
      whatsapp: "رقم واتساب",
      working_hours: "ساعات العمل",
      contract_4_6_months: "مسار عقد 4–6 أشهر",
      analytics: "كتابة التحليلات",
      leads: "كتابة الطلبات",
      configured: "مهيأ",
      notConfigured: "غير مهيأ",
      healthy: "سليم وقابل للكتابة",
      unhealthy: "غير سليم",
      ready: "جاهز",
      notReady: "غير جاهز",
      lastCheck: "آخر فحص: {value}",
      lastRefresh: "آخر تحديث ناجح: {value}",
      calendarRefresh: "آخر تحديث للتقويم: {value}",
      engineRefresh: "آخر لقطة موثقة لمحرك السعر: {value}",
      unavailable: "غير متاح",
      noBlockers: "لا توجد موانع إطلاق حمراء.",
      noContentIssues: "لا توجد تعارضات محتوى مسجلة.",
      noLicenceIssues: "لا توجد مشاكل إعلان أو انتهاء مسجلة.",
      listingId: "الوحدة {id}",
      source: "المصدر {value}",
      created: "طلبات منشأة",
      responded: "رد عليها الفريق",
      booked: "محجوزة",
      lost: "مفقودة",
      notTracked: "غير متتبع بعد",
      percent: "{value}%",
      matcher_to_lead: "إكمال المطابقة إلى طلب",
      lead_to_response: "الطلب إلى رد الفريق",
      lead_to_booking: "الطلب إلى حجز",
      response_to_booking: "رد الفريق إلى حجز",
      responseTime: "متوسط وقت الرد",
      minutes: "{value} دقيقة ({count} طلب)",
      discountRate: "طلبات تخفيض السعر",
      trackedRate: "{numerator} من {denominator}، {rate}%",
      purposes: "أغراض الإقامة",
      places: "معرفات الأماكن المطلوبة",
      durations: "مدد الإقامة",
      lossReasons: "أسباب الخسارة",
      emptyGroup: "لا توجد بيانات مسجلة.",
      work: "عمل أو انتقال",
      family: "إقامة عائلية",
      treatment: "علاج",
      visit: "زيارة",
      "1_month": "شهر واحد",
      "2_3_months": "شهران إلى ثلاثة",
      "4_6_months": "أربعة إلى ستة أشهر",
      price_reason: "السعر",
      unavailable_dates: "التواريخ غير متاحة",
      location: "الموقع",
      space: "المساحة",
      contract_terms: "شروط العقد",
      no_response: "لم يرد العميل",
      booked_elsewhere: "حجز في مكان آخر",
      other: "سبب آخر",
      invalidReference: "أدخل مرجع الطلب الكامل بصيغته الصحيحة.",
      chooseLostReason: "اختر سبب خسارة الطلب.",
      invalidAction: "اختر تحديثًا معتمدًا.",
      submitting: "جاري تسجيل التحديث",
      updateSaved: "تم تسجيل التحديث وتحديث التقارير.",
      apiFailure: "تعذر تحميل بيانات التشغيل",
      apiFailureDetail: "تعذر الوصول إلى البيانات المحلية. استخدم التحديث اليدوي بعد التحقق من الخدمة.",
      authExpired: "انتهت جلسة لوحة عوجا",
      authExpiredDetail: "ارجع إلى لوحة عوجا وسجل الدخول ثم افتح تشغيل السكن الشهري.",
      forbidden: "حسابك لا يملك صلاحية التشغيل الشهري",
      forbiddenDetail: "هذه الصفحة متاحة للمدير وفريق العمليات فقط.",
      disabled: "النسخة الشهرية الجديدة غير مفعلة",
      disabledDetail: "لن تعرض الصفحة بيانات تشغيل حتى تفعيل النسخة الجديدة.",
      funnelUnavailable: "بيانات المسار غير متاحة حاليًا.",
      landing_view: "زيارة صفحة الشهري",
      entry_route_choice: "اختيار المساعدة أو التصفح",
      matcher_start: "بدء المطابقة",
      matcher_answer: "إجابة المطابقة",
      matcher_completion: "إكمال المطابقة",
      results_view: "عرض النتائج",
      result_impression: "ظهور توصية",
      listing_view: "فتح صفحة وحدة",
      whatsapp_click: "الضغط على واتساب",
      lead_created: "إنشاء مرجع الطلب",
      team_response: "رد الفريق",
      booked_stage: "تم الحجز",
      lost_stage: "خسر الطلب"
    },
    en: {
      pageTitle: "Monthly operations · Ouja",
      skipLink: "Skip to content",
      brandLabel: "Ouja monthly operations",
      loadingLabel: "Loading operations data",
      productName: "Monthly operations",
      pageNav: "Page links",
      backDashboard: "Back to Ouja dashboard",
      readinessLabel: "Launch decision",
      loadingTitle: "Checking monthly-stay readiness",
      loadingDetail: "Checking publication, price, availability, and the Ouja team handoff.",
      notChecked: "The check has not completed",
      refresh: "Refresh status",
      refreshing: "Refreshing",
      launchReady: "Operational checks are ready for launch",
      launchBlocked: "Launch is blocked until the issues are resolved",
      readyDetail: "All required publication, contact, and storage checks are healthy.",
      blockedDetail: "{count} red launch blocker needs a clear action.",
      inventoryTitle: "Publication eligibility and coverage",
      inventoryDetail: "Counts use received inventory only, with no duplication or estimates.",
      configurationTitle: "Handoff and continuity settings",
      configurationDetail: "Every missing setting is shown as a launch blocker.",
      blockersTitle: "Red launch blockers",
      blockersDetail: "Each reason includes its code and listing ID when available.",
      contentTitle: "Content conflicts",
      contentDetail: "Title, bedrooms, language, amenities, and publication details.",
      licenceTitle: "Advertising information status",
      licenceDetail: "Missing, expired, and expiring information.",
      funnelTitle: "Monthly lead funnel",
      funnelDetail: "From site entry to team response and outcome, without message content or personal data.",
      stagesTableLabel: "Lead funnel stages",
      stagesCaption: "Sessions or leads at each stage",
      stage: "Stage",
      count: "Count",
      conversionTitle: "Conversion and response time",
      demandTitle: "Recorded demand",
      outcomeTitle: "Lead follow-up workspace",
      outcomeDetail: "Look up the full reference before recording an action. This page does not message customers.",
      leadReference: "Lead reference",
      lookupLead: "View lead",
      lookingUp: "Loading lead",
      lookupFound: "The lead is loaded. Staff controls are now available.",
      leadDetailTitle: "Saved request summary",
      leadJourneyTitle: "Recorded customer journey",
      leadActionsTitle: "Previous staff actions",
      noHomeSelected: "The customer did not select a home for this lead.",
      listingLabel: "Selected listing",
      titleLabel: "Home",
      purposeLabel: "Stay purpose",
      datesLabel: "Dates",
      durationLabel: "Duration",
      residentsLabel: "Residents",
      placeLabel: "Place ID",
      quoteLabel: "Saved official quote",
      includedLabel: "Included",
      utilitiesLabel: "Variable services",
      cleaningLabel: "Cleaning",
      depositLabel: "Deposit and refund",
      paymentMethodsLabel: "Payment methods",
      internetTerm: "Internet",
      maintenanceTerm: "Maintenance",
      createdAt: "Lead created",
      respondedAt: "First team response",
      outcomeLabel: "Outcome",
      notRecorded: "Not recorded",
      emptyJourney: "No approved journey stages are recorded for this lead.",
      emptyActions: "No staff actions are recorded.",
      rankLabel: "Rank {value}",
      entry_guided: "Help me choose",
      entry_browse: "Browse all homes",
      monthsLabel: "{value} months",
      staffActionTitle: "Safe follow-up action",
      staffActionDetail: "This only records an internal action. It does not send a message or open WhatsApp.",
      staffActionLabel: "Action",
      confirm_request: "Confirm request review",
      request_information: "Request missing information",
      prepare_alternative: "Prepare an alternative",
      informationReason: "Information needed",
      alternativeReason: "Alternative reason",
      alternativeListing: "Published alternative listing ID",
      recordAction: "Record action",
      info_dates: "Confirm dates",
      info_residents: "Confirm resident count",
      info_place: "Confirm requested place",
      info_contract_terms: "Confirm requested contract terms",
      info_other: "Other information",
      alternative_lower_price: "Lower price",
      alternative_dates: "Date availability",
      alternative_location: "Better location",
      alternative_space: "Better space",
      alternative_contract_terms: "Contract terms",
      chooseInformationReason: "Choose the information needed",
      chooseAlternativeReason: "Choose the alternative reason",
      invalidInformationReason: "Choose the information needed.",
      invalidAlternativeReason: "Choose the alternative reason.",
      invalidAlternativeListing: "Enter a valid published listing ID.",
      actionSaved: "The action was recorded and the lead and reports were refreshed.",
      preparedTitle: "Prepared alternative summary",
      copyAlternative: "Copy summary",
      copied: "The summary was copied. No message was sent.",
      copyFailed: "Copy failed. Select and copy the text manually.",
      outcomeUpdateTitle: "Record a response or final outcome",
      actionLabel: "Update to record",
      actionResponse: "Record team response",
      actionBooked: "Record booking",
      actionLost: "Record lost lead",
      discountClassification: "Did the customer request a lower price?",
      unknown: "Not classified",
      yes: "Yes",
      no: "No",
      lostReason: "Lost reason",
      chooseReason: "Choose a reason",
      recordUpdate: "Record update",
      received: "Received",
      valid: "Valid",
      blocked: "Blocked",
      published: "Published",
      calendar: "Calendar coverage",
      price: "Official price coverage",
      coverageOf: "{covered} of {total}",
      noInventory: "No received inventory is available for a rate.",
      missingIds: "Missing: {ids}",
      staleIds: "Stale: {ids}",
      noCoverageGaps: "No coverage gaps are recorded.",
      whatsapp: "WhatsApp number",
      working_hours: "Working hours",
      contract_4_6_months: "4–6 month contract route",
      analytics: "Analytics writes",
      leads: "Lead-store writes",
      configured: "Configured",
      notConfigured: "Not configured",
      healthy: "Healthy and writable",
      unhealthy: "Unhealthy",
      ready: "Ready",
      notReady: "Not ready",
      lastCheck: "Last check: {value}",
      lastRefresh: "Last successful refresh: {value}",
      calendarRefresh: "Latest calendar refresh: {value}",
      engineRefresh: "Latest verified pricing-engine snapshot: {value}",
      unavailable: "Unavailable",
      noBlockers: "No red launch blockers.",
      noContentIssues: "No content conflicts are recorded.",
      noLicenceIssues: "No advertising or expiry issues are recorded.",
      listingId: "Listing {id}",
      source: "Source {value}",
      created: "Created leads",
      responded: "Team responses",
      booked: "Booked",
      lost: "Lost",
      notTracked: "Not tracked yet",
      percent: "{value}%",
      matcher_to_lead: "Matcher completion to lead",
      lead_to_response: "Lead to team response",
      lead_to_booking: "Lead to booking",
      response_to_booking: "Response to booking",
      responseTime: "Average response time",
      minutes: "{value} minutes ({count} leads)",
      discountRate: "Lower-price requests",
      trackedRate: "{numerator} of {denominator}, {rate}%",
      purposes: "Stay purposes",
      places: "Requested place IDs",
      durations: "Stay durations",
      lossReasons: "Lost reasons",
      emptyGroup: "No data recorded.",
      work: "Work or relocation",
      family: "Family stay",
      treatment: "Treatment",
      visit: "Visit",
      "1_month": "One month",
      "2_3_months": "Two to three months",
      "4_6_months": "Four to six months",
      price_reason: "Price",
      unavailable_dates: "Dates unavailable",
      location: "Location",
      space: "Space",
      contract_terms: "Contract terms",
      no_response: "No customer response",
      booked_elsewhere: "Booked elsewhere",
      other: "Other",
      invalidReference: "Enter the full lead reference in its correct format.",
      chooseLostReason: "Choose a lost reason.",
      invalidAction: "Choose an approved update.",
      submitting: "Recording update",
      updateSaved: "The update was recorded and the reports were refreshed.",
      apiFailure: "Operations data could not be loaded",
      apiFailureDetail: "Local data could not be reached. Use manual refresh after checking the service.",
      authExpired: "Your Ouja dashboard session has expired",
      authExpiredDetail: "Return to the Ouja dashboard, sign in, then open monthly operations.",
      forbidden: "Your account cannot access monthly operations",
      forbiddenDetail: "This page is available to administrators and operators only.",
      disabled: "The new monthly version is disabled",
      disabledDetail: "Operations data stays closed until the new version is enabled.",
      funnelUnavailable: "Funnel data is currently unavailable.",
      landing_view: "Monthly landing view",
      entry_route_choice: "Guided or browse choice",
      matcher_start: "Matcher start",
      matcher_answer: "Matcher answer",
      matcher_completion: "Matcher completion",
      results_view: "Results view",
      result_impression: "Recommendation impression",
      listing_view: "Listing view",
      whatsapp_click: "WhatsApp click",
      lead_created: "Lead reference created",
      team_response: "Team response",
      booked_stage: "Booked",
      lost_stage: "Lost"
    }
  };

  function normalizeReference(value) {
    const reference = String(value || "").trim().toUpperCase();
    if (!REFERENCE.test(reference)) throw new Error("invalid lead reference");
    return reference;
  }

  function authPath(path, href) {
    const current = new URL(href);
    const target = new URL(path, current.origin);
    if (target.origin !== current.origin) throw new Error("cross-origin path rejected");
    const token = current.searchParams.get("token");
    if (token) target.searchParams.set("token", token);
    return target.pathname + target.search + target.hash;
  }

  function safeRatio(numerator, denominator) {
    const first = Number(numerator);
    const second = Number(denominator);
    if (!Number.isFinite(first) || !Number.isFinite(second) || second <= 0) return null;
    return first / second;
  }

  function isTrackedNumber(value) {
    return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  }

  function buildResponsePayload(reference, classification) {
    const payload = {lead_reference: normalizeReference(reference)};
    if (classification === "yes") payload.discount_requested = true;
    else if (classification === "no") payload.discount_requested = false;
    else if (classification !== "unknown") throw new Error("invalid discount classification");
    return payload;
  }

  function buildOutcomePayload(reference, outcome, reason) {
    const payload = {lead_reference: normalizeReference(reference), outcome: outcome};
    if (outcome === "lost") {
      if (!LOST_REASONS.includes(reason)) throw new Error("lost reason required");
      payload.lost_reason = reason;
    } else if (outcome !== "booked") {
      throw new Error("invalid lead outcome");
    }
    return payload;
  }

  function buildStaffActionPayload(reference, action, values) {
    const payload = {lead_reference: normalizeReference(reference), action: action};
    const fields = values || {};
    if (action === "confirm_request") return payload;
    if (action === "request_information") {
      if (!INFORMATION_REASONS.includes(fields.information_reason)) throw new Error("invalid information reason");
      payload.reason = fields.information_reason;
      return payload;
    }
    if (action === "prepare_alternative") {
      if (!ALTERNATIVE_REASONS.includes(fields.alternative_reason)) throw new Error("invalid alternative reason");
      const listing = String(fields.alternative_listing_id || "").trim();
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(listing)) throw new Error("invalid alternative listing");
      payload.reason = fields.alternative_reason;
      payload.alternative_listing_id = listing;
      return payload;
    }
    throw new Error("invalid staff action");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      authPath, safeRatio, isTrackedNumber, buildResponsePayload,
      buildOutcomePayload, buildStaffActionPayload
    };
  }
  if (typeof document === "undefined") return;

  const state = {
    lang: "ar",
    health: null,
    funnel: null,
    lead: null,
    prepared: null,
    formDirty: false,
    submitting: false,
    refreshing: false
  };

  function text(key, values) {
    let value = COPY[state.lang][key] || COPY.ar[key] || key;
    Object.keys(values || {}).forEach(function (name) {
      value = value.replace("{" + name + "}", String(values[name]));
    });
    return value;
  }

  function node(tag, className, value) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined && value !== null) item.textContent = String(value);
    return item;
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? new Intl.NumberFormat(state.lang === "ar" ? "ar-SA" : "en-US").format(parsed) : "0";
  }

  function dateTime(value) {
    if (!value) return text("unavailable");
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return new Intl.DateTimeFormat(state.lang === "ar" ? "ar-SA" : "en-GB", {
      dateStyle: "medium", timeStyle: "short"
    }).format(parsed);
  }

  function stageLabel(name) {
    if (name === "booked") return text("booked_stage");
    if (name === "lost") return text("lost_stage");
    return text(name);
  }

  function reasonLabel(name) {
    return text(name === "price" ? "price_reason" : name);
  }

  function setCopy() {
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
    document.title = text("pageTitle");
    document.querySelectorAll("[data-copy]").forEach(function (item) {
      item.textContent = text(item.getAttribute("data-copy"));
    });
    document.querySelectorAll("[data-copy-aria]").forEach(function (item) {
      item.setAttribute("aria-label", text(item.getAttribute("data-copy-aria")));
    });
    const language = document.getElementById("ops-language");
    language.textContent = state.lang === "ar" ? "English" : "العربية";
    language.setAttribute("aria-label", state.lang === "ar" ? "Switch to English" : "التبديل إلى العربية");
    renderLostOptions();
    renderStaffReasonOptions();
    if (state.health) renderHealth(state.health);
    if (state.funnel) renderFunnel(state.funnel);
    if (state.lead) renderLead(state.lead);
    if (state.prepared) renderPreparedAlternative(state.prepared);
  }

  function metric(container, label, value) {
    const item = node("div");
    item.append(node("dt", "", label), node("dd", "", number(value)));
    container.append(item);
  }

  function status(container, label, value, tone) {
    const item = node("div");
    item.append(node("dt", "", label), node("dd", "state-text " + tone, value));
    container.append(item);
  }

  function coverage(container, label, covered, total, details) {
    const item = node("div", "coverage-item");
    const head = node("div", "coverage-head");
    const ratio = safeRatio(covered, total);
    head.append(
      node("strong", "", label),
      node("span", "", text("coverageOf", {covered: number(covered), total: number(total)}))
    );
    const track = node("div", "coverage-track");
    const fill = node("div", "coverage-fill");
    if (ratio === null) {
      track.setAttribute("aria-label", text("noInventory"));
    } else {
      const percent = Math.max(0, Math.min(100, Math.round(ratio * 100)));
      track.setAttribute("role", "progressbar");
      track.setAttribute("aria-valuemin", "0");
      track.setAttribute("aria-valuemax", "100");
      track.setAttribute("aria-valuenow", String(percent));
      fill.style.width = percent + "%";
    }
    track.append(fill);
    const notes = [];
    const missing = Array.isArray(details && details.missing_ids) ? details.missing_ids : [];
    const stale = Array.isArray(details && details.stale_ids) ? details.stale_ids : [];
    if (total <= 0) notes.push(text("noInventory"));
    if (missing.length) notes.push(text("missingIds", {ids: missing.join(", ")}));
    if (stale.length) notes.push(text("staleIds", {ids: stale.join(", ")}));
    if (!notes.length) notes.push(text("noCoverageGaps"));
    item.append(head, track, node("p", "coverage-note", notes.join(" · ")));
    container.append(item);
  }

  function issueRow(issue, tone) {
    const row = node("article", "issue-row" + (tone === "warning" ? " warning" : ""));
    const meta = node("div", "issue-meta");
    if (issue && issue.listing_id) {
      meta.append(node("span", "issue-id", text("listingId", {id: issue.listing_id})));
    }
    meta.append(node("span", "code-chip", String((issue && issue.code) || "unknown")));
    const message = issue && (state.lang === "ar" ? issue.message_ar : issue.message_en);
    row.append(meta, node("p", "issue-copy", message || text("unavailable")));
    return row;
  }

  function renderIssueMap(container, values, emptyKey, tone) {
    container.replaceChildren();
    const entries = values && typeof values === "object" ? Object.keys(values).sort() : [];
    entries.forEach(function (listingId) {
      const issues = Array.isArray(values[listingId]) ? values[listingId] : [];
      issues.forEach(function (issue) {
        const safe = Object.assign({}, issue, {listing_id: issue.listing_id || listingId});
        container.append(issueRow(safe, tone));
      });
    });
    if (!container.children.length) container.append(node("p", "empty-line", text(emptyKey)));
  }

  function renderHealth(data) {
    state.health = data;
    const blockers = Array.isArray(data.red_blockers) ? data.red_blockers : [];
    const launch = document.getElementById("launch-panel");
    launch.classList.remove("ready", "blocked");
    launch.classList.add(data.ready ? "ready" : "blocked");
    launch.setAttribute("aria-busy", "false");
    document.getElementById("launch-title").textContent = text(data.ready ? "launchReady" : "launchBlocked");
    document.getElementById("launch-detail").textContent = data.ready
      ? text("readyDetail")
      : text("blockedDetail", {count: number(blockers.length)});
    document.getElementById("checked-at").textContent = text("lastCheck", {value: dateTime(data.checked_at)});
    document.getElementById("last-refresh").textContent = text("lastRefresh", {value: dateTime(data.refresh_time)});
    const sourceTimestamps = data.source_timestamps || {};
    document.getElementById("calendar-refresh").textContent = text("calendarRefresh", {value: dateTime(sourceTimestamps.calendar)});
    document.getElementById("engine-refresh").textContent = text("engineRefresh", {value: dateTime(sourceTimestamps.engine)});

    const counts = data.counts || {};
    const countList = document.getElementById("inventory-counts");
    countList.replaceChildren();
    ["received", "valid", "blocked", "published"].forEach(function (key) {
      metric(countList, text(key), counts[key]);
    });

    const coverageList = document.getElementById("coverage-list");
    coverageList.replaceChildren();
    const coverageValue = data.coverage || {};
    const coverageDetails = data.coverage_details || {};
    coverage(coverageList, text("calendar"), coverageValue.calendar, counts.received, coverageDetails.calendar);
    coverage(coverageList, text("price"), coverageValue.price, counts.received, coverageDetails.price);

    const configuration = document.getElementById("configuration-list");
    configuration.replaceChildren();
    const configured = data.configuration || {};
    status(configuration, text("whatsapp"), text(configured.whatsapp ? "configured" : "notConfigured"), configured.whatsapp ? "ok" : "danger");
    status(configuration, text("working_hours"), text(configured.working_hours ? "configured" : "notConfigured"), configured.working_hours ? "ok" : "danger");
    const contract = data.contract_4_6_months || {};
    status(configuration, text("contract_4_6_months"), text(contract.ready ? "ready" : "notReady"), contract.ready ? "ok" : "danger");
    const analytics = data.analytics || {};
    const analyticsOk = analytics.healthy === true && analytics.write_probe === true;
    status(configuration, text("analytics"), text(analyticsOk ? "healthy" : "unhealthy"), analyticsOk ? "ok" : "danger");
    const leads = data.leads || {};
    const leadsOk = leads.healthy === true && leads.write_probe === true;
    status(configuration, text("leads"), text(leadsOk ? "healthy" : "unhealthy"), leadsOk ? "ok" : "danger");

    const blockerList = document.getElementById("blockers-list");
    blockerList.replaceChildren();
    blockers.forEach(function (issue) { blockerList.append(issueRow(issue, "danger")); });
    if (!blockers.length) blockerList.append(node("p", "empty-line", text("noBlockers")));
    document.getElementById("blocker-count").textContent = number(blockers.length);
    renderIssueMap(document.getElementById("content-conflicts"), data.content_conflicts, "noContentIssues", "danger");
    renderIssueMap(document.getElementById("licence-expiry"), data.licence_expiry, "noLicenceIssues", "warning");
  }

  function conversionRow(container, label, value) {
    const parsed = Number(value);
    status(
      container,
      label,
      isTrackedNumber(value) ? text("percent", {value: number(Math.round(parsed * 1000) / 10)}) : text("notTracked"),
      isTrackedNumber(value) ? "ok" : "warn"
    );
  }

  function demandGroup(container, title, rows, labelFor) {
    const group = node("section", "demand-group");
    group.append(node("h4", "", title));
    if (!rows.length) {
      group.append(node("p", "coverage-note", text("emptyGroup")));
    } else {
      const list = node("ul");
      rows.forEach(function (row) {
        list.append(node("li", "", labelFor(row) + ": " + number(row.count)));
      });
      group.append(list);
    }
    container.append(group);
  }

  function renderFunnel(data) {
    if (data && data.ok === false) throw new Error("funnel unavailable");
    state.funnel = data;
    const leads = data.leads || {};
    const leadCounts = document.getElementById("lead-counts");
    leadCounts.replaceChildren();
    ["created", "responded", "booked", "lost"].forEach(function (key) {
      metric(leadCounts, text(key), leads[key]);
    });

    const stages = document.getElementById("funnel-stages");
    stages.replaceChildren();
    STAGES.forEach(function (name) {
      const row = node("tr");
      row.append(node("th", "", stageLabel(name)), node("td", "", number((data.stages || {})[name])));
      row.firstChild.setAttribute("scope", "row");
      stages.append(row);
    });

    const conversions = document.getElementById("conversion-list");
    conversions.replaceChildren();
    const rates = data.conversion_rates || {};
    ["matcher_to_lead", "lead_to_response", "lead_to_booking", "response_to_booking"].forEach(function (key) {
      conversionRow(conversions, text(key), rates[key]);
    });
    const response = data.response_time_minutes || {};
    const responseCopy = isTrackedNumber(response.average)
      ? text("minutes", {value: number(response.average), count: number(response.count)})
      : text("notTracked");
    status(conversions, text("responseTime"), responseCopy, isTrackedNumber(response.average) ? "ok" : "warn");
    const discount = data.discount_request_rate || {};
    const discountTracked = discount.status === "tracked" && Number(discount.denominator) > 0 && isTrackedNumber(discount.rate);
    status(
      conversions,
      text("discountRate"),
      discountTracked
        ? text("trackedRate", {
          numerator: number(discount.numerator),
          denominator: number(discount.denominator),
          rate: number(Math.round(Number(discount.rate) * 1000) / 10)
        })
        : text("notTracked"),
      discountTracked ? "ok" : "warn"
    );

    const demand = document.getElementById("demand-list");
    demand.replaceChildren();
    demandGroup(demand, text("purposes"), Array.isArray(data.common_purposes) ? data.common_purposes : [], function (row) {
      return PURPOSES.includes(row.purpose) ? text(row.purpose) : String(row.purpose || text("unavailable"));
    });
    demandGroup(demand, text("places"), Array.isArray(data.requested_places) ? data.requested_places : [], function (row) {
      const label = state.lang === "ar" ? row.label_ar : row.label_en;
      const placeId = String(row.place_id || text("unavailable"));
      return label ? String(label) + " (" + placeId + ")" : placeId;
    });
    const durationRows = DURATION_BANDS.map(function (band) {
      return {band: band, count: Number((data.duration_bands || {})[band]) || 0};
    });
    demandGroup(demand, text("durations"), durationRows, function (row) { return text(row.band); });
    const lostRows = LOST_REASONS.map(function (reason) {
      return {reason: reason, count: Number((data.lost_reasons || {})[reason]) || 0};
    });
    demandGroup(demand, text("lossReasons"), lostRows, function (row) { return reasonLabel(row.reason); });
  }

  function showError(kind, keepContent) {
    const panel = document.getElementById("ops-error");
    const title = document.getElementById("ops-error-title");
    const detail = document.getElementById("ops-error-detail");
    const map = {
      auth: ["authExpired", "authExpiredDetail"],
      forbidden: ["forbidden", "forbiddenDetail"],
      disabled: ["disabled", "disabledDetail"],
      api: ["apiFailure", "apiFailureDetail"]
    };
    const keys = map[kind] || map.api;
    title.textContent = text(keys[0]);
    detail.textContent = text(keys[1]);
    panel.hidden = false;
    document.getElementById("loading-state").hidden = true;
    if (!keepContent) document.getElementById("ops-content").hidden = true;
  }

  async function request(path, options) {
    const response = await fetch(authPath(path, window.location.href), Object.assign({
      credentials: "same-origin",
      headers: {"Accept": "application/json"}
    }, options || {}));
    const data = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      const error = new Error("request failed");
      error.kind = response.status === 401 ? "auth" : response.status === 403 ? "forbidden" : response.status === 404 ? "disabled" : "api";
      error.payload = data;
      throw error;
    }
    return data;
  }

  function post(path, payload) {
    return request(path, {
      method: "POST",
      headers: {"Accept": "application/json", "Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
  }

  function funnelFailure() {
    const stages = document.getElementById("funnel-stages");
    stages.replaceChildren();
    const row = node("tr");
    const cell = node("td", "", text("funnelUnavailable"));
    cell.colSpan = 2;
    row.append(cell);
    stages.append(row);
    document.getElementById("lead-counts").replaceChildren();
    const conversions = document.getElementById("conversion-list");
    conversions.replaceChildren();
    status(conversions, text("conversionTitle"), text("funnelUnavailable"), "warn");
    document.getElementById("demand-list").replaceChildren(node("p", "empty-line", text("funnelUnavailable")));
  }

  async function refreshAll(manual) {
    if (state.refreshing) return;
    state.refreshing = true;
    const button = document.getElementById("refresh-ops");
    button.disabled = true;
    button.textContent = text("refreshing");
    if (manual) document.getElementById("ops-error").hidden = true;
    const results = await Promise.allSettled([request(API.health), request(API.funnel)]);
    const rejected = results.find(function (result) { return result.status === "rejected"; });
    if (rejected && ["auth", "forbidden", "disabled"].includes(rejected.reason.kind)) {
      showError(rejected.reason.kind, false);
    } else {
      let anySuccess = false;
      if (results[0].status === "fulfilled") {
        renderHealth(results[0].value);
        anySuccess = true;
      } else {
        showError("api", Boolean(state.health));
      }
      if (results[1].status === "fulfilled") {
        try {
          renderFunnel(results[1].value);
          anySuccess = true;
        } catch (_error) {
          funnelFailure();
          showError("api", true);
        }
      } else {
        funnelFailure();
        showError("api", anySuccess);
      }
      if (anySuccess) {
        document.getElementById("loading-state").hidden = true;
        document.getElementById("ops-content").hidden = false;
      }
    }
    state.refreshing = false;
    button.disabled = false;
    button.textContent = text("refresh");
  }

  function renderLostOptions() {
    const select = document.getElementById("lost-reason");
    const selected = select.value;
    select.replaceChildren();
    const blank = node("option", "", text("chooseReason"));
    blank.value = "";
    select.append(blank);
    LOST_REASONS.forEach(function (reason) {
      const option = node("option", "", reasonLabel(reason));
      option.value = reason;
      select.append(option);
    });
    if (LOST_REASONS.includes(selected)) select.value = selected;
  }

  function renderReasonOptions(select, choices, blankKey, prefix) {
    const selected = select.value;
    select.replaceChildren();
    const blank = node("option", "", text(blankKey));
    blank.value = "";
    select.append(blank);
    choices.forEach(function (reason) {
      const option = node("option", "", text(prefix + reason));
      option.value = reason;
      select.append(option);
    });
    if (choices.includes(selected)) select.value = selected;
  }

  function renderStaffReasonOptions() {
    renderReasonOptions(
      document.getElementById("information-reason"),
      INFORMATION_REASONS,
      "chooseInformationReason",
      "info_"
    );
    renderReasonOptions(
      document.getElementById("alternative-reason"),
      ALTERNATIVE_REASONS,
      "chooseAlternativeReason",
      "alternative_"
    );
  }

  function setFieldError(input, errorLine, message) {
    input.setAttribute("aria-invalid", message ? "true" : "false");
    errorLine.textContent = message || "";
  }

  function clearWorkflowErrors() {
    [
      ["lead-reference", "lead-reference-error"],
      ["staff-action", "staff-action-error"],
      ["information-reason", "information-reason-error"],
      ["alternative-reason", "alternative-reason-error"],
      ["alternative-listing-id", "alternative-listing-error"],
      ["lost-reason", "lost-reason-error"]
    ].forEach(function (ids) {
      setFieldError(document.getElementById(ids[0]), document.getElementById(ids[1]), "");
    });
  }

  function setWorkflowEnabled(enabled) {
    const active = enabled && !state.submitting;
    document.getElementById("staff-action").disabled = !active;
    document.getElementById("submit-staff-action").disabled = !active;
    document.getElementById("lead-action").disabled = !active;
    document.getElementById("discount-requested").disabled = !active;
    document.getElementById("submit-outcome").disabled = !active;
    syncStaffFields();
    syncOutcomeFields();
  }

  function detailRow(container, label, value) {
    const row = node("div");
    row.append(node("dt", "", label), node("dd", "", value || text("notRecorded")));
    container.append(row);
  }

  function durationText(request) {
    if (request.duration_months) return number(request.duration_months) + (state.lang === "ar" ? " شهر" : " months");
    if (request.duration_days) return number(request.duration_days) + (state.lang === "ar" ? " يوم" : " days");
    return text("notRecorded");
  }

  function quoteText(quote) {
    if (!quote || !isTrackedNumber(quote.monthly_rate_sar)) return text("notRecorded");
    const monthly = number(quote.monthly_rate_sar);
    const total = isTrackedNumber(quote.stay_total_sar) ? number(quote.stay_total_sar) : "—";
    return state.lang === "ar"
      ? monthly + " ر.س شهريًا · الإجمالي " + total + " ر.س"
      : "SAR " + monthly + " monthly · SAR " + total + " total";
  }

  function localizedTerm(item) {
    if (!item || typeof item !== "object") return text("notRecorded");
    const label = state.lang === "ar" ? item.label_ar : item.label_en;
    return label || text("notRecorded");
  }

  function includedText(quote) {
    const included = Array.isArray(quote && quote.included) ? quote.included : [];
    const labels = included.map(function (item) {
      if (item === "internet") return text("internetTerm");
      if (item === "maintenance") return text("maintenanceTerm");
      return String(item);
    });
    return labels.length ? labels.join(" · ") : text("notRecorded");
  }

  function depositText(quote) {
    const deposit = quote && quote.deposit;
    if (!deposit || typeof deposit !== "object") return text("notRecorded");
    const amount = isTrackedNumber(deposit.amount_sar)
      ? (state.lang === "ar" ? number(deposit.amount_sar) + " ر.س" : "SAR " + number(deposit.amount_sar))
      : text("notRecorded");
    const refund = state.lang === "ar" ? deposit.refund_ar : deposit.refund_en;
    return refund ? amount + " · " + refund : amount;
  }

  function paymentMethodsText(quote) {
    const payment_methods = Array.isArray(quote && quote.payment_methods) ? quote.payment_methods : [];
    const labels = payment_methods.map(function (item) {
      return item && (state.lang === "ar" ? item.ar : item.en);
    }).filter(Boolean);
    return labels.length ? labels.join(" · ") : text("notRecorded");
  }

  function placeText(place, fallback) {
    if (place && typeof place === "object") {
      const label = state.lang === "ar" ? place.label_ar : place.label_en;
      if (label) return label + (place.id ? " · " + place.id : "");
    }
    return fallback || text("notRecorded");
  }

  function renderLead(data) {
    state.lead = data;
    const detail = document.getElementById("lead-detail-list");
    detail.replaceChildren();
    const requestData = data.request || {};
    const title = data.title && (state.lang === "ar" ? data.title.ar : data.title.en);
    const selected = data.listing_id
      ? String(data.listing_id) + (title ? " · " + title : "")
      : text("noHomeSelected");
    detailRow(detail, text("leadReference"), data.reference);
    detailRow(detail, text("listingLabel"), selected);
    detailRow(detail, text("purposeLabel"), PURPOSES.includes(requestData.purpose) ? text(requestData.purpose) : requestData.purpose);
    detailRow(detail, text("datesLabel"), [requestData.move_in, requestData.move_out].filter(Boolean).join(" – "));
    detailRow(detail, text("durationLabel"), durationText(requestData));
    detailRow(detail, text("residentsLabel"), requestData.residents ? number(requestData.residents) : null);
    detailRow(detail, text("placeLabel"), placeText(requestData.place, requestData.place_id));
    detailRow(detail, text("quoteLabel"), quoteText(data.quote));
    detailRow(detail, text("includedLabel"), includedText(data.quote));
    detailRow(detail, text("utilitiesLabel"), localizedTerm(data.quote && data.quote.utilities));
    detailRow(detail, text("cleaningLabel"), localizedTerm(data.quote && data.quote.cleaning));
    detailRow(detail, text("depositLabel"), depositText(data.quote));
    detailRow(detail, text("paymentMethodsLabel"), paymentMethodsText(data.quote));
    detailRow(detail, text("createdAt"), dateTime(data.created_at));
    detailRow(detail, text("respondedAt"), data.responded_at ? dateTime(data.responded_at) : null);
    detailRow(detail, text("outcomeLabel"), data.outcome ? stageLabel(data.outcome) : null);

    const journeyList = document.getElementById("lead-journey-list");
    journeyList.replaceChildren();
    const lead_journey = Array.isArray(data.journey) ? data.journey : [];
    lead_journey.forEach(function (item) {
      const details = [];
      if (item.listing_id) details.push(text("listingId", {id: item.listing_id}));
      if (item.rank) details.push(text("rankLabel", {value: number(item.rank)}));
      if (["guided", "browse"].includes(item.entry_route)) details.push(text("entry_" + item.entry_route));
      if (item.purpose && PURPOSES.includes(item.purpose)) details.push(text(item.purpose));
      if (item.place_id) details.push(placeText(item.place, String(item.place_id)));
      if (item.duration_months) details.push(text("monthsLabel", {value: number(item.duration_months)}));
      if (item.duration_band && DURATION_BANDS.includes(item.duration_band)) details.push(text(item.duration_band));
      const copy = stageLabel(item.event) + (details.length ? " · " + details.join(" · ") : "");
      journeyList.append(node("li", "", copy));
    });
    if (!journeyList.children.length) journeyList.append(node("li", "empty-line", text("emptyJourney")));

    const actions = document.getElementById("lead-actions-list");
    actions.replaceChildren();
    (Array.isArray(data.actions) ? data.actions : []).forEach(function (item) {
      const details = [text(item.action)];
      if (item.reason) {
        const prefix = item.action === "request_information" ? "info_" : "alternative_";
        details.push(text(prefix + item.reason));
      }
      if (item.alternative_listing_id) details.push(text("listingId", {id: item.alternative_listing_id}));
      details.push(dateTime(item.created_at));
      actions.append(node("li", "", details.join(" · ")));
    });
    if (!actions.children.length) actions.append(node("li", "empty-line", text("emptyActions")));
  }

  function renderPreparedAlternative(data) {
    state.prepared = data;
    const panel = document.getElementById("prepared-alternative");
    const message = state.lang === "ar" ? data.message_ar : data.message_en;
    document.getElementById("prepared-alternative-copy").textContent = message || "";
    panel.hidden = !message;
  }

  function syncStaffFields() {
    const enabled = Boolean(state.lead) && !state.submitting;
    const action = document.getElementById("staff-action").value;
    const information = action === "request_information";
    const alternative = action === "prepare_alternative";
    document.getElementById("information-reason-field").hidden = !information;
    document.getElementById("alternative-reason-field").hidden = !alternative;
    document.getElementById("alternative-listing-field").hidden = !alternative;
    document.getElementById("information-reason").disabled = !enabled || !information;
    document.getElementById("information-reason").required = information;
    document.getElementById("alternative-reason").disabled = !enabled || !alternative;
    document.getElementById("alternative-reason").required = alternative;
    document.getElementById("alternative-listing-id").disabled = !enabled || !alternative;
    document.getElementById("alternative-listing-id").required = alternative;
  }

  function syncOutcomeFields() {
    const action = document.getElementById("lead-action").value;
    const enabled = Boolean(state.lead) && !state.submitting;
    document.getElementById("discount-field").hidden = action !== "response";
    document.getElementById("lost-reason-field").hidden = action !== "lost";
    document.getElementById("discount-requested").disabled = !enabled || action !== "response";
    document.getElementById("lost-reason").disabled = !enabled || action !== "lost";
    document.getElementById("lost-reason").required = action === "lost";
  }

  function apiErrorMessage(error) {
    const payloadError = error && error.payload && error.payload.error;
    return payloadError
      ? (state.lang === "ar" ? payloadError.message_ar : payloadError.message_en)
      : text("apiFailureDetail");
  }

  async function loadLead(showProgress) {
    const reference = document.getElementById("lead-reference");
    const errorLine = document.getElementById("lead-reference-error");
    const statusLine = document.getElementById("lookup-status");
    let normalized;
    setFieldError(reference, errorLine, "");
    try {
      normalized = normalizeReference(reference.value);
    } catch (_error) {
      setFieldError(reference, errorLine, text("invalidReference"));
      reference.focus();
      return false;
    }
    const button = document.getElementById("lead-lookup");
    button.disabled = true;
    if (showProgress) statusLine.textContent = text("lookingUp");
    try {
      const result = await post(API.lead, {lead_reference: normalized});
      if (!result || result.ok !== true || !result.lead) throw new Error("lead lookup rejected");
      state.lead = result.lead;
      reference.value = result.lead.reference;
      renderLead(result.lead);
      document.getElementById("lead-workspace").hidden = false;
      setWorkflowEnabled(true);
      state.formDirty = false;
      if (showProgress) statusLine.textContent = text("lookupFound");
      return true;
    } catch (error) {
      state.lead = null;
      document.getElementById("lead-workspace").hidden = true;
      setWorkflowEnabled(false);
      if (["auth", "forbidden", "disabled"].includes(error.kind)) showError(error.kind, false);
      setFieldError(reference, errorLine, apiErrorMessage(error));
      if (showProgress) statusLine.textContent = "";
      reference.focus();
      return false;
    } finally {
      button.disabled = false;
    }
  }

  async function submitStaffAction(event) {
    event.preventDefault();
    if (state.submitting || !state.lead) return;
    clearWorkflowErrors();
    const actionSelect = document.getElementById("staff-action");
    const information = document.getElementById("information-reason");
    const alternativeReason = document.getElementById("alternative-reason");
    const alternativeListing = document.getElementById("alternative-listing-id");
    const statusLine = document.getElementById("staff-action-status");
    let payload;
    try {
      payload = buildStaffActionPayload(state.lead.reference, actionSelect.value, {
        information_reason: information.value,
        alternative_reason: alternativeReason.value,
        alternative_listing_id: alternativeListing.value
      });
    } catch (_error) {
      if (!STAFF_ACTIONS.includes(actionSelect.value)) {
        setFieldError(actionSelect, document.getElementById("staff-action-error"), text("invalidAction"));
        actionSelect.focus();
      } else if (actionSelect.value === "request_information") {
        setFieldError(information, document.getElementById("information-reason-error"), text("invalidInformationReason"));
        information.focus();
      } else if (!ALTERNATIVE_REASONS.includes(alternativeReason.value)) {
        setFieldError(alternativeReason, document.getElementById("alternative-reason-error"), text("invalidAlternativeReason"));
        alternativeReason.focus();
      } else {
        setFieldError(alternativeListing, document.getElementById("alternative-listing-error"), text("invalidAlternativeListing"));
        alternativeListing.focus();
      }
      return;
    }

    state.submitting = true;
    setWorkflowEnabled(false);
    statusLine.className = "";
    statusLine.textContent = text("submitting");
    try {
      const result = await post(API.action, payload);
      if (!result || result.ok !== true) throw new Error("staff action rejected");
      state.prepared = result.prepared_alternative || null;
      if (state.prepared) renderPreparedAlternative(state.prepared);
      else document.getElementById("prepared-alternative").hidden = true;
      statusLine.className = "success";
      statusLine.textContent = text("actionSaved");
      state.formDirty = false;
      await loadLead(false);
      await refreshAll(true);
    } catch (error) {
      statusLine.className = "error";
      if (["auth", "forbidden", "disabled"].includes(error.kind)) showError(error.kind, false);
      statusLine.textContent = apiErrorMessage(error);
      const field = error.payload && error.payload.error && error.payload.error.field;
      if (field === "alternative_listing_id") {
        setFieldError(alternativeListing, document.getElementById("alternative-listing-error"), statusLine.textContent);
        alternativeListing.focus();
      }
    } finally {
      state.submitting = false;
      if (state.lead) setWorkflowEnabled(true);
    }
  }

  async function submitOutcome(event) {
    event.preventDefault();
    if (state.submitting || !state.lead) return;
    const reference = document.getElementById("lead-reference");
    const action = document.getElementById("lead-action").value;
    const reason = document.getElementById("lost-reason");
    const statusLine = document.getElementById("form-status");
    setFieldError(reference, document.getElementById("lead-reference-error"), "");
    setFieldError(reason, document.getElementById("lost-reason-error"), "");
    let endpoint;
    let payload;
    try {
      if (action === "response") {
        endpoint = API.response;
        payload = buildResponsePayload(state.lead.reference, document.getElementById("discount-requested").value);
      } else if (action === "booked" || action === "lost") {
        endpoint = API.outcome;
        payload = buildOutcomePayload(state.lead.reference, action, reason.value);
      } else {
        throw new Error("invalid action");
      }
    } catch (error) {
      if (!REFERENCE.test(String(state.lead.reference || "").trim().toUpperCase())) {
        setFieldError(reference, document.getElementById("lead-reference-error"), text("invalidReference"));
        statusLine.textContent = text("invalidReference");
        reference.focus();
      } else if (action === "lost" && !LOST_REASONS.includes(reason.value)) {
        setFieldError(reason, document.getElementById("lost-reason-error"), text("chooseLostReason"));
        statusLine.textContent = text("chooseLostReason");
        reason.focus();
      } else {
        statusLine.textContent = text("invalidAction");
      }
      statusLine.className = "error";
      return;
    }

    state.submitting = true;
    setWorkflowEnabled(false);
    statusLine.className = "";
    statusLine.textContent = text("submitting");
    try {
      const result = await post(endpoint, payload);
      if (!result || result.ok !== true) throw new Error("update rejected");
      statusLine.className = "success";
      statusLine.textContent = text("updateSaved");
      state.formDirty = false;
      document.getElementById("lead-outcome-form").reset();
      syncOutcomeFields();
      await loadLead(false);
      await refreshAll(true);
    } catch (error) {
      statusLine.className = "error";
      if (["auth", "forbidden", "disabled"].includes(error.kind)) showError(error.kind, false);
      statusLine.textContent = apiErrorMessage(error);
    } finally {
      state.submitting = false;
      if (state.lead) setWorkflowEnabled(true);
    }
  }

  async function copyPreparedAlternative() {
    const statusLine = document.getElementById("copy-status");
    const value = document.getElementById("prepared-alternative-copy").textContent;
    try {
      if (!value || !navigator.clipboard || !navigator.clipboard.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(value);
      statusLine.className = "success";
      statusLine.textContent = text("copied");
    } catch (_error) {
      statusLine.className = "error";
      statusLine.textContent = text("copyFailed");
    }
  }

  document.getElementById("ops-language").addEventListener("click", function () {
    state.lang = state.lang === "ar" ? "en" : "ar";
    setCopy();
  });
  document.getElementById("ops-dashboard-link").addEventListener("click", function (event) {
    event.preventDefault();
    window.location.assign(authPath("/dashboard", window.location.href));
  });
  document.getElementById("refresh-ops").addEventListener("click", function () { refreshAll(true); });
  document.getElementById("lead-lookup-form").addEventListener("submit", function (event) {
    event.preventDefault();
    loadLead(true);
  });
  document.getElementById("lead-reference").addEventListener("input", function () {
    const current = state.lead && state.lead.reference;
    const entered = String(this.value || "").trim().toUpperCase();
    state.formDirty = true;
    if (current && entered !== current) {
      state.lead = null;
      state.prepared = null;
      document.getElementById("lead-workspace").hidden = true;
      setWorkflowEnabled(false);
    }
  });
  document.getElementById("staff-action").addEventListener("change", syncStaffFields);
  document.getElementById("staff-action-form").addEventListener("input", function () { state.formDirty = true; });
  document.getElementById("staff-action-form").addEventListener("change", function () { state.formDirty = true; });
  document.getElementById("staff-action-form").addEventListener("submit", submitStaffAction);
  document.getElementById("copy-alternative").addEventListener("click", copyPreparedAlternative);
  document.getElementById("lead-action").addEventListener("change", syncOutcomeFields);
  document.getElementById("lead-outcome-form").addEventListener("input", function () { state.formDirty = true; });
  document.getElementById("lead-outcome-form").addEventListener("change", function () { state.formDirty = true; });
  document.getElementById("lead-outcome-form").addEventListener("submit", submitOutcome);

  setCopy();
  renderStaffReasonOptions();
  setWorkflowEnabled(false);
  syncStaffFields();
  syncOutcomeFields();
  refreshAll(false);
  window.setInterval(function () {
    if (!state.formDirty) refreshAll(false);
  }, 60000);
}());
