(function () {
  "use strict";

  const FACTS = ["parking", "elevator", "workspace", "kitchen", "washer", "private_entrance", "compound", "accessibility", "balcony", "pool"];
  const STEPS = ["identity", "space", "location", "content", "terms", "sources", "approval"];
  const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
  const PURPOSES = ["work", "family", "treatment", "visit"];
  const PLACE_CATEGORIES = ["business_hubs", "hospitals", "family_retail", "riyadh_season", "events"];
  const DAY_LABELS = {
    ar: { monday: "الاثنين", tuesday: "الثلاثاء", wednesday: "الأربعاء", thursday: "الخميس", friday: "الجمعة", saturday: "السبت", sunday: "الأحد" },
    en: { monday: "Monday", tuesday: "Tuesday", wednesday: "Wednesday", thursday: "Thursday", friday: "Friday", saturday: "Saturday", sunday: "Sunday" }
  };
  const SOURCE_LABELS = {
    ar: { connected_listing: "بيانات الشقة المرتبطة", stay_approved: "محتوى عوجا المعتمد", monthly_licence_store: "سجل معلومات الإعلان", monthly_approved: "بيانات شهرية معتمدة", monthly_draft: "مسودة الفريق" },
    en: { connected_listing: "connected apartment data", stay_approved: "approved Ouja content", monthly_licence_store: "advertising information record", monthly_approved: "approved monthly data", monthly_draft: "team draft" }
  };
  const BLOCKER_LABELS = {
    active_missing: { ar: "حدد ظهور الشقة في السكن الشهري", en: "Choose whether the apartment is visible for monthly stays" },
    arabic_title_missing: { ar: "اسم الشقة بالعربي ناقص", en: "Arabic apartment name is missing" },
    arabic_title_language_mismatch: { ar: "اسم الشقة العربي يحتاج نصًا عربيًا", en: "Arabic apartment name needs Arabic text" },
    english_title_missing: { ar: "اسم الشقة بالإنجليزي ناقص", en: "English apartment name is missing" },
    english_title_language_mismatch: { ar: "اسم الشقة الإنجليزي يحتاج نصًا إنجليزيًا", en: "English apartment name needs English text" },
    arabic_content_missing: { ar: "الوصف العربي ناقص", en: "Arabic description is missing" },
    arabic_content_language_mismatch: { ar: "المحتوى العربي يحتاج نصًا عربيًا مكتملًا", en: "Arabic content needs complete Arabic text" },
    english_content_missing: { ar: "الوصف الإنجليزي ناقص", en: "English description is missing" },
    english_content_language_mismatch: { ar: "المحتوى الإنجليزي يحتاج نصًا إنجليزيًا مكتملًا", en: "English content needs complete English text" },
    content_unverified: { ar: "راجع المحتوى باللغتين", en: "Review the content in both languages" },
    bedrooms_missing: { ar: "عدد غرف النوم ناقص", en: "Bedroom count is missing" },
    bathrooms_missing: { ar: "عدد دورات المياه ناقص", en: "Bathroom count is missing" },
    capacity_missing: { ar: "عدد السكان ناقص", en: "Resident capacity is missing" },
    neighbourhood_missing: { ar: "بيانات الحي الموثقة ناقصة", en: "Verified neighborhood details are missing" },
    neighbourhood_language_mismatch: { ar: "أسماء الحي تحتاج العربي والإنجليزي الصحيح", en: "Neighborhood names need valid Arabic and English text" },
    images_missing: { ar: "تحتاج الشقة ثلاث صور على الأقل", en: "The apartment needs at least three photos" },
    licence_missing: { ar: "معلومات الإعلان ناقصة", en: "Advertising information is missing" },
    commercial_terms_missing: { ar: "شروط الخدمات والتنظيف ناقصة", en: "Utilities and cleaning terms are missing" },
    commercial_terms_language_mismatch: { ar: "شروح الشروط تحتاج العربي والإنجليزي الصحيح", en: "Terms need valid Arabic and English explanations" },
    price_missing: { ar: "السعر الشهري الرسمي ناقص", en: "Official monthly price is missing" },
    calendar_missing: { ar: "تغطية التقويم ناقصة", en: "Calendar coverage is missing" },
    calendar_stale: { ar: "بيانات التقويم قديمة", en: "Calendar data is stale" },
    calendar_future: { ar: "وقت تحديث التقويم غير صحيح", en: "Calendar refresh time is invalid" },
    calendar_invalid: { ar: "بيانات التقويم غير صالحة", en: "Calendar data is invalid" },
    rating_unverified: { ar: "التقييم غير موثق", en: "Rating is not verified" },
    rating_invalid: { ar: "بيانات التقييم غير صالحة", en: "Rating data is invalid" },
    source_refresh_failed: { ar: "آخر تحديث للمصدر لم ينجح", en: "The latest source refresh failed" },
    catalog_incomplete: { ar: "بيانات المخزون المستلمة غير مكتملة", en: "Received inventory data is incomplete" },
    licence_expiry_missing: { ar: "تاريخ انتهاء معلومات الإعلان ناقص", en: "Advertising expiry date is missing" },
    licence_expiry_invalid: { ar: "تاريخ انتهاء معلومات الإعلان غير صحيح", en: "Advertising expiry date is invalid" },
    licence_expired: { ar: "معلومات الإعلان منتهية", en: "Advertising information has expired" },
    title_bedroom_conflict: { ar: "اسم الشقة يتعارض مع عدد غرف النوم", en: "Apartment name conflicts with the bedroom count" },
    untranslated_amenity: { ar: "إحدى المزايا غير مترجمة", en: "An amenity is not translated" },
    coordinates_unverified: { ar: "إحداثيات الشقة غير موثقة", en: "Apartment coordinates are not verified" },
    listing_id_missing: { ar: "معرّف الشقة ناقص", en: "Apartment ID is missing" }
  };
  const FIELD_LABELS = {
    active: { ar: "ظهور الشقة", en: "Apartment visibility" },
    name_ar: { ar: "اسم الشقة بالعربي", en: "Arabic apartment name" },
    name_en: { ar: "اسم الشقة بالإنجليزي", en: "English apartment name" },
    short_ar: { ar: "الوصف المختصر بالعربي", en: "Short Arabic description" },
    short_en: { ar: "الوصف المختصر بالإنجليزي", en: "Short English description" },
    content_verified: { ar: "مراجعة المحتوى", en: "Content review" },
    bedrooms: { ar: "غرف النوم", en: "Bedrooms" },
    beds_count: { ar: "عدد الأسرّة", en: "Beds" },
    baths: { ar: "دورات المياه", en: "Bathrooms" },
    capacity: { ar: "عدد السكان", en: "Residents" },
    floor_area_sqm: { ar: "المساحة بالمتر", en: "Area in sqm" },
    neighborhood: { ar: "معرّف الحي", en: "Neighborhood ID" },
    neighborhood_ar: { ar: "اسم الحي بالعربي", en: "Arabic neighborhood" },
    neighborhood_en: { ar: "اسم الحي بالإنجليزي", en: "English neighborhood" },
    neighborhood_verified: { ar: "التحقق من الحي", en: "Neighborhood verification" },
    coordinates: { ar: "إحداثيات الشقة", en: "Apartment coordinates" },
    "licence.licence_no": { ar: "رقم معلومات الإعلان", en: "Advertising information number" },
    "licence.expires": { ar: "تاريخ انتهاء معلومات الإعلان", en: "Advertising expiry date" },
    "structured.tagline_ar": { ar: "عبارة الشقة بالعربي", en: "Arabic tagline" },
    "structured.tagline_en": { ar: "عبارة الشقة بالإنجليزي", en: "English tagline" },
    "structured.sections.*.title_ar": { ar: "عنوان القسم بالعربي", en: "Arabic section title" },
    "structured.sections.*.title_en": { ar: "عنوان القسم بالإنجليزي", en: "English section title" },
    "structured.sections.*.body_ar": { ar: "تفاصيل القسم بالعربي", en: "Arabic section details" },
    "structured.sections.*.body_en": { ar: "تفاصيل القسم بالإنجليزي", en: "English section details" },
    "commercial_terms.utilities.mode": { ar: "احتساب الخدمات", en: "Utilities" },
    "commercial_terms.utilities.label_ar": { ar: "شرح الخدمات بالعربي", en: "Arabic utilities explanation" },
    "commercial_terms.utilities.label_en": { ar: "شرح الخدمات بالإنجليزي", en: "English utilities explanation" },
    "commercial_terms.cleaning.mode": { ar: "التنظيف", en: "Cleaning" },
    "commercial_terms.cleaning.amount_sar": { ar: "قيمة التنظيف", en: "Cleaning amount" },
    "commercial_terms.cleaning.label_ar": { ar: "شرح التنظيف بالعربي", en: "Arabic cleaning explanation" },
    "commercial_terms.cleaning.label_en": { ar: "شرح التنظيف بالإنجليزي", en: "English cleaning explanation" }
  };

  function translatedBlocker(code, lang) {
    const language = lang === "en" ? "en" : "ar", value = BLOCKER_LABELS[code];
    return value ? value[language] : String(code || "").replace(/_/g, " ");
  }

  function issueFieldLabel(field, lang) {
    const language = lang === "en" ? "en" : "ar";
    const key = String(field || "").replace(/structured\.sections\.\d+\./, "structured.sections.*.");
    const value = FIELD_LABELS[key];
    return value ? value[language] : String(field || "").replace(/_/g, " ");
  }

  function fieldStep(field) {
    const value = String(field || "");
    if (/^(active|name_|licence\.|images)/.test(value)) return "identity";
    if (/^(bedrooms|beds_count|baths|capacity|floor_area_sqm|facts\.)/.test(value)) return "space";
    if (/^(neighborhood|coordinates)/.test(value)) return "location";
    if (/^(short_|content_verified|structured\.)/.test(value)) return "content";
    if (/^commercial_terms\./.test(value)) return "terms";
    return null;
  }

  function summarizePlaces(rows) {
    const categories = {}, allowed = new Set(PLACE_CATEGORIES);
    Object.keys(rows && typeof rows === "object" ? rows : {}).forEach(function (key) {
      const row = rows[key], approved = row && row.approved;
      const category = approved && approved.category_id;
      if (!row || row.active !== true || !approved || !allowed.has(category)) return;
      categories[category] = (categories[category] || 0) + 1;
    });
    return { total: Object.values(categories).reduce(function (sum, count) { return sum + count; }, 0), categories: categories };
  }

  function formatDistance(value, lang) {
    const distance = Number(value);
    if (!Number.isFinite(distance) || distance < 0) return "";
    return distance.toFixed(1) + (lang === "en" ? " km straight-line" : " كم بخط مستقيم");
  }

  function translatedDay(day, lang) {
    const language = lang === "en" ? "en" : "ar";
    return DAY_LABELS[language][day] || day;
  }

  function prefillSourceLabel(sources, path, lang) {
    const language = lang === "en" ? "en" : "ar", key = String(path || "").split(".")[0];
    const rawSource = sources && sources[key];
    const source = rawSource === ["host", "away_listing"].join("") ? "connected_listing" : rawSource;
    const label = SOURCE_LABELS[language][source];
    if (!label) return "";
    return (language === "ar" ? "المصدر: " : "Source: ") + label;
  }

  function authPath(path, search) {
    const token = new URLSearchParams(typeof search === "string" ? search : "").get("token");
    return token ? path + "?token=" + encodeURIComponent(token) : path;
  }

  function buildFactValue(value) {
    if (value === true || value === "yes") return true;
    if (value === false || value === "no") return false;
    return null;
  }

  function parseCoordinatePair(value) {
    if (value && typeof value === "object") {
      const lat = Number(value.lat), lng = Number(value.lng);
      return Number.isFinite(lat) && Number.isFinite(lng) ? { lat: lat, lng: lng } : null;
    }
    const text = String(value || "").trim();
    const patterns = [
      /^\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)\s*,\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)\s*$/,
      /@(-?[0-9]{1,3}(?:\.[0-9]+)?),(-?[0-9]{1,3}(?:\.[0-9]+)?)/,
      /[?&](?:q|query|destination)=(-?[0-9]{1,3}(?:\.[0-9]+)?),\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)/i
    ];
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) return { lat: Number(match[1]), lng: Number(match[2]) };
    }
    return null;
  }

  function present(value) { return value !== undefined && value !== null && value !== ""; }
  function clone(value) { return value && typeof value === "object" ? JSON.parse(JSON.stringify(value)) : {}; }
  function retainConflictDraft(latest, localDraft) {
    const result = clone(latest);
    result.serverDraft = clone(result.draft);
    result.draft = clone(localDraft);
    return result;
  }
  function approvalOutcome(result) {
    const value = result && typeof result === "object" ? result : {}, refresh = value.refresh || {};
    if (refresh.accepted === true && value.published === true) return "approval_published";
    if (refresh.accepted === true) return "approval_blocked";
    if (refresh.pending === true) return "approval_pending";
    return "approval_failed";
  }
  function number(value, integer) {
    if (!present(value)) return undefined;
    const result = integer ? Number.parseInt(value, 10) : Number(value);
    return Number.isFinite(result) ? result : undefined;
  }

  function buildProfilePayload(raw) {
    const source = raw && typeof raw === "object" ? raw : {}, profile = {};
    ["active", "content_verified", "neighborhood_verified"].forEach(function (key) {
      if (typeof source[key] === "boolean") profile[key] = source[key];
    });
    ["name_ar", "name_en", "short_ar", "short_en", "neighborhood", "neighborhood_ar", "neighborhood_en"].forEach(function (key) {
      if (present(source[key])) profile[key] = String(source[key]).trim();
    });
    ["bedrooms", "beds_count", "baths", "capacity"].forEach(function (key) {
      const value = number(source[key], true); if (value !== undefined) profile[key] = value;
    });
    const area = number(source.floor_area_sqm, false); if (area !== undefined) profile.floor_area_sqm = area;
    if (Array.isArray(source.images)) profile.images = source.images.filter(function (url) { return typeof url === "string" && url.trim(); });
    if (source.facts && typeof source.facts === "object") {
      profile.facts = {};
      FACTS.forEach(function (key) { if (Object.prototype.hasOwnProperty.call(source.facts, key)) profile.facts[key] = buildFactValue(source.facts[key]); });
    }
    if (source.licence && present(source.licence.licence_no) && present(source.licence.expires)) {
      profile.licence = { licence_no: String(source.licence.licence_no).trim(), expires: String(source.licence.expires).trim() };
    }
    if (source.structured && typeof source.structured === "object") {
      const structured = {};
      ["tagline_ar", "tagline_en", "neighborhood_ar", "neighborhood_en"].forEach(function (key) {
        if (present(source.structured[key])) structured[key] = String(source.structured[key]).trim();
      });
      if (Array.isArray(source.structured.emblems)) structured.emblems = clone(source.structured.emblems);
      if (Array.isArray(source.structured.sections)) {
        const sections = source.structured.sections.map(function (item) {
          return { title_ar: String(item.title_ar || "").trim(), title_en: String(item.title_en || "").trim(), body_ar: String(item.body_ar || "").trim(), body_en: String(item.body_en || "").trim() };
        }).filter(function (item) { return item.title_ar || item.title_en || item.body_ar || item.body_en; });
        if (sections.length) structured.sections = sections;
      }
      if (Object.keys(structured).length) profile.structured = structured;
    }
    const pair = parseCoordinatePair(source.coordinates);
    if (pair) profile.coordinates = { lat: pair.lat, lng: pair.lng, source: source.coordinates && source.coordinates.source || "staff_maps_pin", verified: !(source.coordinates && source.coordinates.source === "guide_title_match") };
    if (source.commercial_terms && typeof source.commercial_terms === "object") {
      const utilities = source.commercial_terms.utilities || {}, cleaning = source.commercial_terms.cleaning || {}, amount = number(cleaning.amount_sar, false);
      profile.commercial_terms = {
        utilities: { mode: String(utilities.mode || ""), label_ar: String(utilities.label_ar || "").trim(), label_en: String(utilities.label_en || "").trim() },
        cleaning: { mode: String(cleaning.mode || ""), amount_sar: amount === undefined ? null : amount, label_ar: String(cleaning.label_ar || "").trim(), label_en: String(cleaning.label_en || "").trim() }
      };
    }
    return profile;
  }

  function buildSettingsPayload(raw) {
    const source = raw && typeof raw === "object" ? raw : {}, schedule = {}, included = [];
    DAYS.forEach(function (day) {
      const item = source.schedule && source.schedule[day];
      if (item && item.enabled) schedule[day] = [[String(item.start || ""), String(item.end || "")]];
    });
    if (source.internet_included === true) included.push("internet");
    if (source.maintenance_included === true) included.push("maintenance");
    return {
      whatsapp_number: String(source.whatsapp_number || "").replace(/[^0-9]/g, ""),
      working_hours: { timezone: String(source.timezone || "Asia/Riyadh"), schedule: schedule },
      commercial_terms: {
        included: included,
        deposit: { amount_sar: number(source.deposit_amount_sar, false), refund_ar: String(source.deposit_refund_ar || "").trim(), refund_en: String(source.deposit_refund_en || "").trim() },
        payment_methods: (Array.isArray(source.payment_methods) ? source.payment_methods : []).map(function (item) { return { ar: String(item.ar || "").trim(), en: String(item.en || "").trim() }; }).filter(function (item) { return item.ar || item.en; })
      },
      long_stay_route: String(source.long_stay_route || "").trim()
    };
  }

  function buildPlacePayload(raw) {
    const source = raw && typeof raw === "object" ? raw : {}, pair = parseCoordinatePair(source.coordinates);
    return {
      label_ar: String(source.label_ar || "").trim(), label_en: String(source.label_en || "").trim(),
      purposes: Array.from(new Set((Array.isArray(source.purposes) ? source.purposes : []).filter(function (item) { return PURPOSES.includes(item); }))),
      coordinates: pair ? { lat: pair.lat, lng: pair.lng, source: "staff_maps_pin", verified: true } : String(source.coordinates || "").trim(),
      source_note: String(source.source_note || "").trim()
    };
  }

  function matchesLanguage(value, language) {
    if (!present(value)) return false;
    return language === "ar" ? /[\u0600-\u06ff]/.test(String(value)) : /[A-Za-z]/.test(String(value));
  }

  function structuredLanguageReady(profile, language) {
    const structured = profile && profile.structured;
    if (!structured || typeof structured !== "object") return true;
    const suffix = language === "ar" ? "_ar" : "_en";
    for (const key of ["tagline" + suffix, "neighborhood" + suffix]) {
      if (present(structured[key]) && !matchesLanguage(structured[key], language)) return false;
    }
    for (const emblem of Array.isArray(structured.emblems) ? structured.emblems : []) {
      if (!emblem || !matchesLanguage(emblem[language], language)) return false;
    }
    for (const section of Array.isArray(structured.sections) ? structured.sections : []) {
      if (!section || !matchesLanguage(section["title" + suffix], language) || !matchesLanguage(section["body" + suffix], language)) return false;
    }
    return true;
  }

  function profileReadiness(profile) {
    const value = profile && typeof profile === "object" ? profile : {};
    if (value.active === false) return { percent: 100, ready_for_approval: true, staff_blockers: [] };
    const terms = value.commercial_terms || {}, utilities = terms.utilities || {}, cleaning = terms.cleaning || {};
    const termsPresent = ["included", "variable", "excluded"].includes(utilities.mode)
      && ["included", "optional", "unavailable"].includes(cleaning.mode)
      && present(utilities.label_ar) && present(utilities.label_en)
      && present(cleaning.label_ar) && present(cleaning.label_en)
      && (cleaning.mode !== "optional" || (Number.isFinite(Number(cleaning.amount_sar)) && Number(cleaning.amount_sar) >= 0));
    const termsLanguageReady = matchesLanguage(utilities.label_ar, "ar")
      && matchesLanguage(utilities.label_en, "en")
      && matchesLanguage(cleaning.label_ar, "ar")
      && matchesLanguage(cleaning.label_en, "en");
    const checks = [
      ["active_missing", value.active === true],
      [!present(value.name_ar) ? "arabic_title_missing" : "arabic_title_language_mismatch", matchesLanguage(value.name_ar, "ar")],
      [!present(value.name_en) ? "english_title_missing" : "english_title_language_mismatch", matchesLanguage(value.name_en, "en")],
      [!present(value.short_ar) ? "arabic_content_missing" : "arabic_content_language_mismatch", matchesLanguage(value.short_ar, "ar") && structuredLanguageReady(value, "ar")],
      [!present(value.short_en) ? "english_content_missing" : "english_content_language_mismatch", matchesLanguage(value.short_en, "en") && structuredLanguageReady(value, "en")],
      ["content_unverified", value.content_verified === true],
      ["bedrooms_missing", Number.isInteger(Number(value.bedrooms))],
      ["bathrooms_missing", Number.isInteger(Number(value.baths))],
      ["capacity_missing", Number.isInteger(Number(value.capacity))],
      [
        present(value.neighborhood_ar) && present(value.neighborhood_en)
          ? "neighbourhood_language_mismatch"
          : "neighbourhood_missing",
        Boolean(value.neighborhood && value.neighborhood_verified === true)
          && matchesLanguage(value.neighborhood_ar, "ar")
          && matchesLanguage(value.neighborhood_en, "en")
      ],
      ["images_missing", Array.isArray(value.images) && value.images.length >= 3],
      ["licence_missing", Boolean(value.licence && value.licence.licence_no && value.licence.expires)],
      [termsPresent ? "commercial_terms_language_mismatch" : "commercial_terms_missing", termsPresent && termsLanguageReady]
    ];
    const blockers = checks.filter(function (item) { return !item[1]; }).map(function (item) { return item[0]; });
    return {
      percent: Math.round(100 * (checks.length - blockers.length) / checks.length),
      ready_for_approval: blockers.length === 0,
      staff_blockers: blockers
    };
  }

  function completionPercent(profile) {
    return profileReadiness(profile).percent;
  }

  function filterListings(listings, filters) {
    const seen = new Set(), query = String(filters && filters.search || "").trim().toLocaleLowerCase(), status = String(filters && filters.status || "all"), blocker = String(filters && filters.blocker || "all");
    return (Array.isArray(listings) ? listings : []).filter(function (row) {
      const id = String(row && row.id || "");
      if (!id || seen.has(id)) return false;
      seen.add(id);
      const text = [id, row.source_title, row.public_title_ar, row.public_title_en, row.neighborhood_ar, row.neighborhood_en].join(" ").toLocaleLowerCase();
      const blockers = [].concat(row.staff_blockers || [], row.background_blockers || []).join(" ").toLocaleLowerCase();
      return (!query || text.includes(query)) && (status === "all" || row.status === status) && (blocker === "all" || blockers.includes(blocker));
    });
  }

  const exported = { authPath, buildFactValue, parseCoordinatePair, buildProfilePayload, buildSettingsPayload, buildPlacePayload, profileReadiness, completionPercent, translatedBlocker, issueFieldLabel, fieldStep, summarizePlaces, formatDistance, filterListings, translatedDay, prefillSourceLabel, retainConflictDraft, approvalOutcome };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  if (typeof document === "undefined") return;

  const AR = {
    identity: "الهوية والصور", space: "المساحة والمزايا", location: "الموقع", content: "المحتوى العربي والإنجليزي", terms: "الشروط الشهرية", sources: "جاهزية المصادر", approval: "المراجعة والاعتماد",
    received: "مستلمة", review: "تحتاج مراجعة", approved: "معتمدة", published: "منشورة", source_blocked: "محجوبة من المصدر", ready_for_approval: "جاهزة للاعتماد", open: "راجع الشقة", noRows: "لا توجد شقق تطابق البحث.", complete: "مكتملة", apartment: "شقة",
    active: "تظهر في السكن الشهري", name_ar: "اسم الشقة بالعربي", name_en: "اسم الشقة بالإنجليزي", licence_no: "رقم معلومات الإعلان", expires: "تاريخ الانتهاء", images: "الصور المتصلة",
    bedrooms: "غرف النوم", beds_count: "عدد الأسرّة", baths: "دورات المياه", capacity: "عدد السكان", floor_area_sqm: "المساحة بالمتر", yes: "نعم", no: "لا", unknown: "غير مجاب",
    parking: "موقف", elevator: "مصعد", workspace: "مساحة عمل", kitchen: "مطبخ", washer: "غسالة", private_entrance: "مدخل خاص", compound: "مجمع", accessibility: "سهولة وصول", balcony: "شرفة", pool: "مسبح",
    neighborhood: "معرّف الحي", neighborhood_ar: "اسم الحي بالعربي", neighborhood_en: "اسم الحي بالإنجليزي", neighborhood_verified: "تم التحقق من الحي", coordinates: "إحداثيات الشقة أو رابط Google Maps",
    short_ar: "الوصف المختصر بالعربي", short_en: "الوصف المختصر بالإنجليزي", content_verified: "راجعت المحتوى باللغتين", tagline_ar: "عبارة الشقة بالعربي", tagline_en: "عبارة الشقة بالإنجليزي", section_title_ar: "عنوان القسم بالعربي", section_title_en: "عنوان القسم بالإنجليزي", section_body_ar: "تفاصيل القسم بالعربي", section_body_en: "تفاصيل القسم بالإنجليزي", addSection: "إضافة قسم محتوى",
    utilities: "احتساب الخدمات", cleaning: "التنظيف", included: "مشمولة", variable: "متغيرة", excluded: "غير مشمولة", optional: "اختياري", unavailable: "غير متاح", amount: "القيمة بالريال", label_ar: "الشرح بالعربي", label_en: "الشرح بالإنجليزي",
    priceMonths: "أشهر السعر الرسمي", calendar: "التقويم", rating: "التقييم الموثق", licence: "معلومات الإعلان", ready: "جاهز", missing: "ناقص", staff: "بيانات تحتاج إكمال", background: "عوائق المصدر الحي", none: "لا توجد عوائق حالياً.",
    saved: "حُفظت المسودة.", approval_published: "تم اعتماد الشقة ونشر النسخة الآمنة.", approval_blocked: "تم اعتماد الشقة، لكنها غير منشورة حتى تُحل عوائق المصدر.", approval_pending: "تم اعتماد الشقة، وتحديث الموقع بانتظار دورة التحديث التالية.", approval_failed: "تم اعتماد الشقة، لكن تحديث الموقع لم ينجح. النسخة السابقة ما زالت آمنة.", conflict: "حفظ شخص آخر نسخة أحدث. حمّلنا رقم النسخة الأحدث وأبقينا تعديلاتك في الحقول للمراجعة وإعادة الحفظ.", conflictCompare: "قارن التغييرات قبل إعادة الحفظ", serverVersion: "نسخة الفريق المحفوظة", yourVersion: "تعديلاتك الحالية", invalid: "راجع الحقل المحدد وأكمل البيانات المطلوبة.", unauthorized: "انتهت صلاحية الدخول. افتح الصفحة من لوحة عوجا مرة أخرى.", forbidden: "صلاحيتك لا تسمح بالتعديل.", service: "الخدمة غير متاحة مؤقتاً، والبيانات المعتمدة لم تتأثر.",
    whatsapp: "رقم واتساب بصيغة دولية", timezone: "المنطقة الزمنية", workingHours: "أوقات الرد", from: "من", to: "إلى", internetIncluded: "أؤكد أن الإنترنت مشمول", maintenanceIncluded: "أؤكد أن الصيانة مشمولة", deposit: "مبلغ التأمين (ر.س)", refund_ar: "شروط الاسترداد بالعربي", refund_en: "شروط الاسترداد بالإنجليزي", payment_ar: "طريقة الدفع بالعربي", payment_en: "طريقة الدفع بالإنجليزي", addPayment: "إضافة طريقة دفع", longRoute: "مسار مراجعة 4–6 أشهر", settingsSaved: "حُفظت مسودة الإعدادات.", settingsApproved: "تم اعتماد الإعدادات.",
    place_id: "معرّف داخلي للمكان", place_ar: "اسم المكان بالعربي", place_en: "اسم المكان بالإنجليزي", purposes: "أغراض الإقامة", place_coordinates: "إحداثيات المكان أو رابط Google Maps", source_note: "دليل التحقق المختصر", activePlace: "فعّال للموقع", edit: "تعديل", placeSaved: "حُفظت مسودة المكان.", placeApproved: "تم اعتماد المكان.", noPlaces: "لا توجد أماكن معتمدة بعد.", work: "عمل أو انتقال", family: "عائلة", treatment: "علاج", visit: "زيارة", refreshOk: "تم طلب تحديث النسخة الآمنة.",
    approvedDestinations: "مكان معتمد", business_hubs: "مراكز الأعمال", hospitals: "المستشفيات", family_retail: "وجهات العائلة والتسوق", riyadh_season: "موسم الرياض", events: "الفعاليات والمعارض", nearestPlaces: "أقرب 5 أماكن معتمدة", nearestDetail: "المسافة محسوبة بخط مستقيم بين نقطتين موثقتين، وليست وقت قيادة.", nearbyNoPin: "وثّق إحداثيات الشقة أولًا حتى نحسب أقرب الأماكن بدون تخمين.", nearbyEmpty: "لا توجد أماكن معتمدة يمكن حساب المسافة لها حاليًا.", straightLine: "بخط مستقيم", openMap: "فتح الخريطة", coordinateProof: "مصدر الإحداثيات", officialProof: "المصدر الرسمي", verifiedOn: "تم التحقق", reviewEvery: "المراجعة"
  };
  const EN = Object.assign({}, AR, {
    identity: "Identity and photos", space: "Space and facts", location: "Location", content: "Arabic and English content", terms: "Monthly terms", sources: "Source readiness", approval: "Review and approval",
    received: "Received", review: "Needs review", approved: "Approved", published: "Published", source_blocked: "Blocked by source", ready_for_approval: "Ready to approve", open: "Review apartment", noRows: "No apartments match the filters.", complete: "complete", apartment: "Apartment",
    active: "Visible for monthly stays", name_ar: "Arabic apartment name", name_en: "English apartment name", licence_no: "Advertising information number", expires: "Expiry date", images: "Connected photos", bedrooms: "Bedrooms", beds_count: "Beds", baths: "Bathrooms", capacity: "Residents", floor_area_sqm: "Area in sqm", yes: "Yes", no: "No", unknown: "Unanswered",
    neighborhood: "Neighborhood ID", neighborhood_ar: "Arabic neighborhood", neighborhood_en: "English neighborhood", neighborhood_verified: "Neighborhood verified", coordinates: "Apartment coordinates or Google Maps URL", short_ar: "Short Arabic description", short_en: "Short English description", content_verified: "I reviewed both languages", tagline_ar: "Arabic tagline", tagline_en: "English tagline", section_title_ar: "Arabic section title", section_title_en: "English section title", section_body_ar: "Arabic section details", section_body_en: "English section details", addSection: "Add content section",
    utilities: "Utilities", cleaning: "Cleaning", included: "Included", variable: "Variable", excluded: "Excluded", optional: "Optional", unavailable: "Unavailable", amount: "Amount in SAR", label_ar: "Arabic explanation", label_en: "English explanation", priceMonths: "Official-price months", calendar: "Calendar", rating: "Verified rating", licence: "Advertising information", ready: "Ready", missing: "Missing", staff: "Staff data to complete", background: "Live-source blockers", none: "No current blockers.",
    saved: "Draft saved.", approval_published: "The apartment was approved and the safe snapshot was published.", approval_blocked: "The apartment was approved but is not published until source blockers are resolved.", approval_pending: "The apartment was approved. Website refresh is waiting for the next refresh pass.", approval_failed: "The apartment was approved, but website refresh failed. The previous safe snapshot remains active.", conflict: "Someone saved a newer version. The latest revision is loaded and your edits remain in the fields for review and retry.", conflictCompare: "Compare changes before saving again", serverVersion: "Saved team version", yourVersion: "Your current edits", invalid: "Review the relevant field and complete the required data.", unauthorized: "Your access expired. Reopen this page from the Ouja dashboard.", forbidden: "Your role cannot make this change.", service: "The service is temporarily unavailable. Approved data was not changed.",
    whatsapp: "WhatsApp number in international format", timezone: "Timezone", workingHours: "Response hours", from: "From", to: "To", internetIncluded: "I confirm internet is included", maintenanceIncluded: "I confirm maintenance is included", deposit: "Deposit (SAR)", refund_ar: "Arabic refund terms", refund_en: "English refund terms", payment_ar: "Arabic payment method", payment_en: "English payment method", addPayment: "Add payment method", longRoute: "4–6 month review route", settingsSaved: "Settings draft saved.", settingsApproved: "Settings approved.",
    place_id: "Internal place ID", place_ar: "Arabic place name", place_en: "English place name", purposes: "Stay purposes", place_coordinates: "Place coordinates or Google Maps URL", source_note: "Short verification evidence", activePlace: "Active on website", edit: "Edit", placeSaved: "Place draft saved.", placeApproved: "Place approved.", noPlaces: "No approved places yet.", work: "Work or relocation", family: "Family", treatment: "Treatment", visit: "Visit", refreshOk: "Safe snapshot refresh requested.",
    approvedDestinations: "approved destinations", business_hubs: "Business hubs", hospitals: "Hospitals", family_retail: "Family retail", riyadh_season: "Riyadh Season", events: "Events and exhibitions", nearestPlaces: "Nearest 5 approved places", nearestDetail: "Distance is straight-line between two verified pins, not driving time.", nearbyNoPin: "Verify the apartment pin first so nearby places can be calculated without guessing.", nearbyEmpty: "No approved destinations can be measured right now.", straightLine: "straight-line", openMap: "Open map", coordinateProof: "Coordinate source", officialProof: "Official source", verifiedOn: "Verified", reviewEvery: "Review cadence"
  });
  const COPY = {
    ar: { skipLink: "انتقل إلى المحتوى", productName: "بيانات الشقق", dashboard: "لوحة عوجا", contextLabel: "السكن الشهري", pageTitle: "جهّز كل شقة للنشر من مكان واحد", pageDetail: "راجع البيانات المعبأة تلقائيًا، أكمل الناقص، ثم اعتمدها للموقع.", refreshData: "تحديث البيانات", apartmentsTab: "الشقق", settingsTab: "الإعدادات المشتركة", placesTab: "الأماكن المعتمدة", loadFailed: "تعذر تحميل بيانات الشقق", loadFailedDetail: "حاول التحديث، ولن تتأثر البيانات المعتمدة الحالية.", globalTitle: "إعدادات تُكتب مرة واحدة", globalDetail: "رقم التواصل، أوقات الرد، التأمين، طرق الدفع، ومسار الإقامات من أربعة إلى ستة أشهر.", saveDraft: "حفظ المسودة", approveSettings: "اعتماد الإعدادات", portfolioTitle: "الشقق المستلمة", portfolioDetail: "صف واحد لكل شقة فعلية، مع الناقص والخطوة التالية.", searchLabel: "ابحث برقم الشقة أو الاسم", searchPlaceholder: "مثال: 101 أو الملقا", statusLabel: "الحالة", allStatuses: "كل الحالات", needsReview: "تحتاج مراجعة", readyApproval: "جاهزة للاعتماد", published: "منشورة", sourceBlocked: "محجوبة من مصدر حي", blockerLabel: "الناقص", allBlockers: "كل الأسباب", licence: "معلومات الإعلان", price: "السعر الرسمي", calendar: "التقويم", content: "المحتوى", backToApartments: "العودة للشقق", surveyTitle: "مراجعة الشقة", previewReadiness: "معاينة الجاهزية", approveAndRefresh: "اعتماد وتحديث الموقع", placesTitle: "الأماكن المهمة للعملاء", placesDetail: "أدخل المكان مرة واحدة، ولا يظهر القرب إلا بعد اعتماد إحداثيات الطرفين.", addPlace: "إضافة مكان", approvePlace: "اعتماد المكان" },
    en: { skipLink: "Skip to content", productName: "Apartment data", dashboard: "Ouja dashboard", contextLabel: "Monthly stays", pageTitle: "Prepare every apartment for publishing in one place", pageDetail: "Review trusted prefills, complete what is missing, then approve it for the website.", refreshData: "Refresh data", apartmentsTab: "Apartments", settingsTab: "Shared settings", placesTab: "Approved places", loadFailed: "Apartment data could not be loaded", loadFailedDetail: "Try refreshing. Current approved data remains unchanged.", globalTitle: "Settings entered once", globalDetail: "Contact number, response hours, deposit, payments, and the four-to-six-month route.", saveDraft: "Save draft", approveSettings: "Approve settings", portfolioTitle: "Received apartments", portfolioDetail: "One row per real apartment, showing the gap and next step.", searchLabel: "Search by apartment ID or name", searchPlaceholder: "For example: 101 or Al Malqa", statusLabel: "Status", allStatuses: "All statuses", needsReview: "Needs review", readyApproval: "Ready to approve", published: "Published", sourceBlocked: "Blocked by live source", blockerLabel: "Missing item", allBlockers: "All reasons", licence: "Advertising information", price: "Official price", calendar: "Calendar", content: "Content", backToApartments: "Back to apartments", surveyTitle: "Review apartment", previewReadiness: "Preview readiness", approveAndRefresh: "Approve and refresh website", placesTitle: "Customer destinations", placesDetail: "Enter each destination once. Proximity appears only after both pins are verified.", addPlace: "Add place", approvePlace: "Approve place" }
  };
  const state = { lang: "ar", listings: [], counts: {}, listing: null, profile: {}, step: "identity", settings: null, places: {}, placeId: "", placeRevision: 0 };
  const id = function (value) { return document.getElementById(value); };
  const text = function (key) { return (state.lang === "ar" ? AR : EN)[key] || translatedBlocker(key, state.lang); };

  function node(tag, values) {
    const result = document.createElement(tag), options = values || {};
    if (options.className) result.className = options.className;
    if (options.text !== undefined) result.textContent = String(options.text);
    ["id", "type", "name", "src", "alt", "placeholder"].forEach(function (key) { if (options[key] !== undefined) result[key] = options[key]; });
    if (options.value !== undefined && options.value !== null) result.value = String(options.value);
    if (options.checked !== undefined) result.checked = Boolean(options.checked);
    if (options.readOnly) result.readOnly = true;
    return result;
  }
  function safeExternalLink(url, label) {
    if (typeof url !== "string" || !/^https:\/\//.test(url)) return null;
    const link = node("a", { text: label });
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }
  function empty(root) { while (root && root.firstChild) root.removeChild(root.firstChild); }
  function add(root) { for (let index = 1; index < arguments.length; index += 1) if (arguments[index]) root.appendChild(arguments[index]); return root; }
  function applyCopy() {
    document.documentElement.lang = state.lang; document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
    document.querySelectorAll("[data-copy]").forEach(function (item) { const value = COPY[state.lang][item.dataset.copy]; if (value) item.textContent = value; });
    document.querySelectorAll("[data-copy-placeholder]").forEach(function (item) { const value = COPY[state.lang][item.dataset.copyPlaceholder]; if (value) item.placeholder = value; });
    id("catalog-language").textContent = state.lang === "ar" ? "English" : "العربية";
  }
  function failureMessage(error) {
    if (error.status === 401) return text("unauthorized"); if (error.status === 403) return text("forbidden");
    if (error.status === 409 || error.code === "revision_conflict") return text("conflict");
    if (error.status === 400) {
      const issue = error.payload && error.payload.issue;
      if (!issue) return text("invalid");
      const message = issue[state.lang === "ar" ? "message_ar" : "message_en"] || text("invalid");
      const label = issue.field && issueFieldLabel(issue.field, state.lang);
      return label ? label + ": " + message : message;
    }
    if (error.status === 503) return text("service");
    return text("service");
  }
  function displayValue(value) {
    if (value === undefined) return "—";
    if (value === null) return "null";
    return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
  }
  function renderConflictComparison(root, record) {
    if (!root || !record || !record.serverDraft) return;
    const server = record.serverDraft, local = record.draft || {}, keys = Array.from(new Set(Object.keys(server).concat(Object.keys(local)))).sort();
    const changed = keys.filter(function (key) { return JSON.stringify(server[key]) !== JSON.stringify(local[key]); });
    if (!changed.length) return;
    const details = node("details", { className: "conflict-comparison" }); details.open = true;
    details.appendChild(node("summary", { text: text("conflictCompare") }));
    changed.forEach(function (key) {
      const row = node("div", { className: "conflict-row" });
      add(row, node("strong", { text: key.replace(/_/g, " ") }), node("span", { text: text("serverVersion") }), node("pre", { text: displayValue(server[key]) }), node("span", { text: text("yourVersion") }), node("pre", { text: displayValue(local[key]) }));
      details.appendChild(row);
    });
    root.appendChild(details);
  }
  function editorError(target, error, record) {
    const parent = target.parentNode, old = parent && parent.querySelector(".conflict-comparison");
    if (old) old.remove();
    target.textContent = failureMessage(error);
    if (error.status === 409 && parent) renderConflictComparison(parent, record);
  }
  function clearEditorConflict(target) {
    const parent = target.parentNode, old = parent && parent.querySelector(".conflict-comparison");
    if (old) old.remove();
  }
  async function api(path, options) {
    const config = Object.assign({ credentials: "same-origin", headers: { Accept: "application/json" } }, options || {});
    if (config.body) config.headers["Content-Type"] = "application/json";
    const response = await fetch(authPath(path, window.location.search), config); let payload = {};
    try { payload = await response.json(); } catch (_error) { payload = {}; }
    if (!response.ok || payload.ok !== true) { const error = new Error(payload.error || "catalog_unavailable"); error.status = response.status; error.code = payload.error; error.payload = payload; throw error; }
    return payload.result;
  }
  function globalError(error) { id("catalog-error-detail").textContent = failureMessage(error); id("catalog-error").hidden = false; }
  function show(panel) {
    ["portfolio", "global-setup", "places", "survey"].forEach(function (name) { id(name).hidden = name !== panel; });
    document.querySelectorAll(".workspace-tab").forEach(function (tab) { const active = tab.dataset.panel === panel; tab.classList.toggle("active", active); tab.setAttribute("aria-selected", active ? "true" : "false"); });
  }
  function statusName(value) { return text(value); }
  function blockers(row) { return [].concat(row.staff_blockers || [], row.background_blockers || []); }
  function renderSummary() {
    const root = id("catalog-summary"), band = node("dl", { className: "summary-band" }); empty(root);
    [["received", "received"], ["review", "needs_review"], ["approved", "approved"], ["published", "published"]].forEach(function (item) { const cell = node("div", { className: "summary-item" }); add(cell, node("dt", { text: text(item[0]) }), node("dd", { text: state.counts[item[1]] || 0 })); band.appendChild(cell); });
    root.appendChild(band); root.setAttribute("aria-busy", "false");
  }
  function currentFilters() { return { search: id("listing-search").value, status: id("status-filter").value, blocker: id("blocker-filter").value }; }
  function renderRows() {
    const rows = filterListings(state.listings, currentFilters()), root = id("listing-table"); empty(root); id("portfolio-count").textContent = rows.length + " / " + state.listings.length;
    if (!rows.length) { root.appendChild(node("p", { className: "empty-row", text: text("noRows") })); return; }
    rows.forEach(function (row) {
      const item = node("article", { className: "listing-row" }), picture = row.first_image && /^https:\/\//.test(row.first_image) ? node("img", { className: "listing-cover", src: row.first_image, alt: "" }) : node("div", { className: "listing-cover", text: row.id });
      if (picture.tagName === "IMG") { picture.loading = "lazy"; picture.referrerPolicy = "no-referrer"; }
      const name = node("div", { className: "listing-name" }); add(name, node("strong", { text: row[state.lang === "ar" ? "public_title_ar" : "public_title_en"] || row.source_title }), node("span", { text: text("apartment") + " " + row.id }));
      const progress = node("div", { className: "desktop-secondary" }), track = node("div", { className: "progress-track" }), fill = node("span"); fill.style.width = row.completion_percent + "%"; track.appendChild(fill); add(progress, node("span", { text: row.completion_percent + "% " + text("complete") }), track);
      const chip = node("span", { className: "status-chip " + (row.status === "published" || row.status === "ready_for_approval" ? "ready" : row.status === "source_blocked" ? "blocked" : "warning"), text: statusName(row.status) });
      const gap = node("span", { className: "status-text desktop-secondary", text: blockers(row).length ? text(blockers(row)[0]) : text("none") });
      const button = node("button", { type: "button", className: "button button-secondary", text: text("open") }); button.addEventListener("click", function () { openListing(row.id); });
      add(item, picture, name, progress, chip, gap, button); root.appendChild(item);
    });
  }
  async function loadRows() { const result = await api("/api/monthly/ops/listings"); state.listings = result.listings || []; state.counts = result.counts || {}; renderSummary(); renderRows(); }

  function field(labelText, path, value, options) {
    const config = options || {}, label = node("label", { className: config.full ? "span-all" : "" }); label.appendChild(node("span", { text: labelText })); let control;
    if (config.kind === "textarea") control = node("textarea", { name: path, value: value || "" });
    else if (config.kind === "select") { control = node("select", { name: path }); (config.options || []).forEach(function (choice) { const option = node("option", { value: choice[0], text: choice[1] }); if (String(choice[0]) === String(value)) option.selected = true; control.appendChild(option); }); }
    else control = node("input", { type: config.type || "text", name: path, value: value === undefined || value === null ? "" : value, readOnly: config.readOnly });
    label.appendChild(control);
    if (state.listing && state.listing.prefill) {
      const source = prefillSourceLabel(state.listing.prefill.sources, path, state.lang);
      if (source) label.appendChild(node("small", { className: "field-source", text: source }));
    }
    return label;
  }
  function check(labelText, path, checked) { const label = node("label", { className: "check-field" }), input = node("input", { type: "checkbox", name: path, checked: checked }); add(label, input, node("span", { text: labelText })); return label; }
  function get(target, path) { return path.split(".").reduce(function (value, key) { return value && value[key]; }, target); }
  function set(target, path, value) {
    const parts = path.split("."); let current = target;
    parts.forEach(function (part, index) { if (index === parts.length - 1) current[part] = value; else { if (!current[part] || typeof current[part] !== "object") current[part] = /^\d+$/.test(parts[index + 1]) ? [] : {}; current = current[part]; } });
  }
  function section(title, detail) { const result = node("section", { className: "survey-section" }); add(result, node("h3", { text: text(title) }), node("p", { text: detail || (state.lang === "ar" ? "معبأ تلقائيًا من بيانات عوجا الموثوقة. عدّل فقط إذا كان غير صحيح." : "Prefilled from trusted Ouja data. Change it only when incorrect.") })); return result; }
  function grid() { return node("div", { className: "form-grid" }); }
  function coordinate(value) { return value && typeof value === "object" ? value.lat + "," + value.lng : value || ""; }
  function renderIdentity(root) {
    const p = state.profile, part = section("identity"), form = grid();
    add(form, check(text("active"), "active", p.active === true), field(text("name_ar"), "name_ar", p.name_ar), field(text("name_en"), "name_en", p.name_en), field(text("licence_no"), "licence.licence_no", get(p, "licence.licence_no")), field(text("expires"), "licence.expires", get(p, "licence.expires"), { type: "date" }));
    const images = node("div", { className: "image-review span-all" }); images.appendChild(node("strong", { text: text("images") + ": " + (p.images || []).length })); const strip = node("div", { className: "image-strip" });
    (p.images || []).slice(0, 8).forEach(function (url) { if (/^https:\/\//.test(url)) { const image = node("img", { src: url, alt: "" }); image.loading = "lazy"; image.referrerPolicy = "no-referrer"; strip.appendChild(image); } }); images.appendChild(strip); form.appendChild(images); part.appendChild(form); root.appendChild(part);
  }
  function renderSpace(root) {
    const p = state.profile, part = section("space"), form = grid();
    ["bedrooms", "beds_count", "baths", "capacity", "floor_area_sqm"].forEach(function (key) { form.appendChild(field(text(key), key, p[key], { type: "number" })); });
    FACTS.forEach(function (key) { const value = p.facts && p.facts[key]; form.appendChild(field(text(key), "facts." + key, value === true ? "yes" : value === false ? "no" : "unknown", { kind: "select", options: [["unknown", text("unknown")], ["yes", text("yes")], ["no", text("no")]] })); });
    part.appendChild(form); root.appendChild(part);
  }
  function renderLocation(root) {
    const p = state.profile, part = section("location", state.lang === "ar" ? "لا نظهر وقت وصول أو قرب إلا بعد التحقق من إحداثيات الشقة والمكان." : "Travel time or proximity appears only after both pins are verified."), form = grid();
    add(form, field(text("neighborhood"), "neighborhood", p.neighborhood), field(text("neighborhood_ar"), "neighborhood_ar", p.neighborhood_ar), field(text("neighborhood_en"), "neighborhood_en", p.neighborhood_en), check(text("neighborhood_verified"), "neighborhood_verified", p.neighborhood_verified === true), field(text("coordinates"), "coordinates", coordinate(p.coordinates), { full: true })); part.appendChild(form); part.appendChild(renderNearestPlaces()); root.appendChild(part);
  }
  function renderNearestPlaces() {
    const panel = node("section", { className: "nearest-places" });
    add(panel, node("h4", { text: text("nearestPlaces") }), node("p", { className: "nearest-detail", text: text("nearestDetail") }));
    const coordinates = state.profile && state.profile.coordinates;
    if (!coordinates || typeof coordinates !== "object" || coordinates.verified !== true) {
      panel.appendChild(node("p", { className: "nearest-empty", text: text("nearbyNoPin") }));
      return panel;
    }
    const places = state.listing && Array.isArray(state.listing.nearest_places) ? state.listing.nearest_places : [];
    if (!places.length) {
      panel.appendChild(node("p", { className: "nearest-empty", text: text("nearbyEmpty") }));
      return panel;
    }
    const list = node("div", { className: "nearest-place-list" });
    places.slice(0, 5).forEach(function (place) {
      const row = node("article", { className: "nearest-place-row" });
      const identity = node("div", { className: "nearest-place-identity" });
      add(
        identity,
        node("strong", { text: place[state.lang === "ar" ? "label_ar" : "label_en"] || place.id }),
        node("span", { text: place[state.lang === "ar" ? "category_ar" : "category_en"] || text(place.category_id) })
      );
      const evidence = node("div", { className: "nearest-place-evidence" });
      evidence.appendChild(node("strong", { className: "nearest-distance", text: formatDistance(place.distance_km, state.lang) }));
      const cadence = place[state.lang === "ar" ? "review_interval_ar" : "review_interval_en"];
      evidence.appendChild(node("span", { className: "place-meta", text: [place.verified_at ? text("verifiedOn") + " " + place.verified_at : "", cadence ? text("reviewEvery") + ": " + cadence : ""].filter(Boolean).join(" · ") }));
      const links = node("div", { className: "nearest-place-links" });
      add(links, safeExternalLink(place.map_url, text("openMap")), safeExternalLink(place.coordinate_source_url, text("coordinateProof")), safeExternalLink(place.official_source_url, text("officialProof")));
      add(row, identity, evidence, links); list.appendChild(row);
    });
    panel.appendChild(list);
    return panel;
  }
  function renderContent(root) {
    const p = state.profile, part = section("content"), form = grid(); p.structured = p.structured || {}; p.structured.sections = Array.isArray(p.structured.sections) && p.structured.sections.length ? p.structured.sections : [{ title_ar: "", title_en: "", body_ar: "", body_en: "" }];
    add(form, field(text("short_ar"), "short_ar", p.short_ar, { kind: "textarea", full: true }), field(text("short_en"), "short_en", p.short_en, { kind: "textarea", full: true }), check(text("content_verified"), "content_verified", p.content_verified === true), field(text("tagline_ar"), "structured.tagline_ar", p.structured.tagline_ar), field(text("tagline_en"), "structured.tagline_en", p.structured.tagline_en));
    p.structured.sections.forEach(function (item, index) { const group = node("fieldset", { className: "content-section span-all" }); group.appendChild(node("legend", { text: text("content") + " " + (index + 1) })); const fields = grid(); add(fields, field(text("section_title_ar"), "structured.sections." + index + ".title_ar", item.title_ar), field(text("section_title_en"), "structured.sections." + index + ".title_en", item.title_en), field(text("section_body_ar"), "structured.sections." + index + ".body_ar", item.body_ar, { kind: "textarea" }), field(text("section_body_en"), "structured.sections." + index + ".body_en", item.body_en, { kind: "textarea" })); group.appendChild(fields); form.appendChild(group); });
    if (p.structured.sections.length < 4) { const button = node("button", { type: "button", className: "button button-secondary span-all", text: text("addSection") }); button.addEventListener("click", function () { p.structured.sections.push({ title_ar: "", title_en: "", body_ar: "", body_en: "" }); renderSurvey(); }); form.appendChild(button); }
    part.appendChild(form); root.appendChild(part);
  }
  function renderTerms(root) {
    const p = state.profile, part = section("terms"), form = grid(); p.commercial_terms = p.commercial_terms || { utilities: {}, cleaning: {} }; const utilities = p.commercial_terms.utilities || {}, cleaning = p.commercial_terms.cleaning || {};
    add(form, field(text("utilities"), "commercial_terms.utilities.mode", utilities.mode || "", { kind: "select", options: [["", "—"], ["included", text("included")], ["variable", text("variable")], ["excluded", text("excluded")]] }), field(text("label_ar"), "commercial_terms.utilities.label_ar", utilities.label_ar), field(text("label_en"), "commercial_terms.utilities.label_en", utilities.label_en), field(text("cleaning"), "commercial_terms.cleaning.mode", cleaning.mode || "", { kind: "select", options: [["", "—"], ["included", text("included")], ["optional", text("optional")], ["unavailable", text("unavailable")]] }), field(text("amount"), "commercial_terms.cleaning.amount_sar", cleaning.amount_sar, { type: "number" }), field(text("label_ar"), "commercial_terms.cleaning.label_ar", cleaning.label_ar), field(text("label_en"), "commercial_terms.cleaning.label_en", cleaning.label_en)); part.appendChild(form); root.appendChild(part);
  }
  function readiness(label, value, ready) { const card = node("div", { className: "readiness-card" }); add(card, node("span", { text: label }), node("strong", { text: value || "—" }), node("span", { className: "status-chip " + (ready ? "ready" : "blocked"), text: text(ready ? "ready" : "missing") })); return card; }
  function renderSources(root) {
    const source = state.listing.source_readiness || {}, part = section("sources", state.lang === "ar" ? "هذه معلومات للعرض فقط وتتحدث من النسخة الآمنة." : "These read-only values come from the safe snapshot."), cards = node("div", { className: "readiness-grid" }), months = source.price_months || [];
    add(cards, readiness(text("priceMonths"), months.join("، "), months.length > 0), readiness(text("calendar"), source.calendar && Object.keys(source.calendar).length, Boolean(source.calendar && Object.keys(source.calendar).length)), readiness(text("rating"), source.rating && source.rating.rating, Boolean(source.rating && source.rating.rating)), readiness(text("images"), source.image_count, source.image_count >= 3), readiness(text("licence"), source.licence_present ? text("ready") : "—", source.licence_present)); part.appendChild(cards); root.appendChild(part);
  }
  function issueGroup(title, values) { const box = node("div", { className: "blocker-group" }); box.appendChild(node("h4", { text: title })); if (!values || !values.length) box.appendChild(node("p", { text: text("none") })); else { const list = node("ul"); values.forEach(function (value) { list.appendChild(node("li", { text: translatedBlocker(value, state.lang) })); }); box.appendChild(list); } return box; }
  function renderApproval(root) { const part = section("approval", state.lang === "ar" ? "الاعتماد ينشر فقط بعد نجاح فحوص الشقة والمصادر الحية." : "Approval publishes only after listing and live-source checks pass."), readiness = profileReadiness(buildProfilePayload(state.profile)); part.appendChild(node("strong", { className: "approval-meter", text: readiness.percent + "% " + text("complete") })); part.appendChild(issueGroup(text("staff"), readiness.staff_blockers)); part.appendChild(issueGroup(text("background"), state.listing.background_blockers)); root.appendChild(part); }
  function updateCompletion() { const readiness = profileReadiness(buildProfilePayload(state.profile)), percent = readiness.percent, root = id("survey-completion"), track = node("div", { className: "progress-track" }), fill = node("span"); empty(root); root.appendChild(node("strong", { text: percent + "%" })); fill.style.width = percent + "%"; track.appendChild(fill); root.appendChild(track); }
  function renderSurvey() {
    const root = id("survey-sections"), progress = id("survey-progress"); empty(root); empty(progress);
    STEPS.forEach(function (step) { const button = node("button", { type: "button", className: state.step === step ? "active" : "", text: text(step) }); button.addEventListener("click", function () { state.step = step; renderSurvey(); }); progress.appendChild(button); });
    ({ identity: renderIdentity, space: renderSpace, location: renderLocation, content: renderContent, terms: renderTerms, sources: renderSources, approval: renderApproval })[state.step](root);
    root.querySelectorAll("input,select,textarea").forEach(function (control) { const update = function () { let value = control.type === "checkbox" ? control.checked : control.value; set(state.profile, control.name, value); control.removeAttribute("aria-invalid"); updateCompletion(); }; control.addEventListener("input", update); control.addEventListener("change", update); }); updateCompletion();
  }
  async function openListing(listingId) {
    try { const result = await api("/api/monthly/ops/listing/" + encodeURIComponent(listingId)); state.listing = result; state.profile = clone(result.prefill); delete state.profile.sources; delete state.profile.source_readiness; state.step = "identity"; id("survey-source-title").textContent = result.source_title; id("survey-meta").textContent = text("apartment") + " " + result.id; id("survey-save-status").textContent = ""; show("survey"); renderSurvey(); }
    catch (error) { globalError(error); }
  }
  function surveyError(error) {
    const issue = error.payload && error.payload.issue;
    if (issue && issue.field) {
      const step = fieldStep(issue.field);
      if (step && state.step !== step) { state.step = step; renderSurvey(); }
    }
    const panel = id("survey-error-summary"); empty(panel);
    panel.appendChild(node("p", { text: failureMessage(error) }));
    if (error.status === 409) renderConflictComparison(panel, state.listing);
    panel.hidden = false;
    if (issue && issue.field) {
      const control = Array.from(id("survey-form").elements).find(function (control) { return control.name === issue.field; });
      if (control) {
        control.setAttribute("aria-invalid", "true");
        control.focus();
        return;
      }
    }
    panel.focus();
  }
  async function recoverProfileConflict(error, localDraft) {
    if (error.status !== 409 || !state.listing) return false;
    try {
      const latest = await api("/api/monthly/ops/listing/" + encodeURIComponent(state.listing.id));
      state.listing = retainConflictDraft(latest, localDraft);
      state.profile = clone(localDraft);
      renderSurvey();
    } catch (_reloadError) { return false; }
    return true;
  }
  async function saveProfile(preview) {
    try { const saved = await api("/api/monthly/ops/listing/" + encodeURIComponent(state.listing.id) + "/draft", { method: "POST", body: JSON.stringify({ revision: state.listing.draft_revision, profile: buildProfilePayload(state.profile) }) }); state.listing.draft_revision = saved.draft_revision; id("survey-save-status").textContent = text("saved"); empty(id("survey-error-summary")); id("survey-error-summary").hidden = true; const refreshed = await api("/api/monthly/ops/listing/" + encodeURIComponent(state.listing.id)); state.listing = refreshed; state.profile = clone(refreshed.prefill); delete state.profile.sources; delete state.profile.source_readiness; if (preview) state.step = "approval"; renderSurvey(); return refreshed; }
    catch (error) { await recoverProfileConflict(error, state.profile); surveyError(error); throw error; }
  }
  async function approveProfile() {
    try { const listing = await saveProfile(false), result = await api("/api/monthly/ops/listing/" + encodeURIComponent(listing.id) + "/approve", { method: "POST", body: JSON.stringify({ revision: listing.draft_revision }) }), outcome = approvalOutcome(result); await loadRows(); await openListing(listing.id); state.step = "approval"; renderSurvey(); id("survey-save-status").textContent = text(outcome) + (result.background_blockers && result.background_blockers.length ? " · " + result.background_blockers.map(text).join("، ") : ""); }
    catch (_error) { return; }
  }

  function schedule(value, day) { const periods = value && value.working_hours && value.working_hours.schedule && value.working_hours.schedule[day]; return Array.isArray(periods) && periods[0] ? { enabled: true, start: periods[0][0], end: periods[0][1] } : { enabled: false, start: "13:00", end: "21:00" }; }
  function renderSettings() {
    const record = state.settings, value = clone(record.draft || record.approved || record.effective || {}), commercial = value.commercial_terms || {}, included = commercial.included || [], deposit = commercial.deposit || {}, root = id("global-fields"), form = grid(); empty(root);
    add(form, field(text("whatsapp"), "whatsapp_number", value.whatsapp_number), field(text("timezone"), "timezone", value.working_hours && value.working_hours.timezone || "Asia/Riyadh"), check(text("internetIncluded"), "internet_included", included.includes("internet")), check(text("maintenanceIncluded"), "maintenance_included", included.includes("maintenance")), field(text("deposit"), "deposit_amount_sar", deposit.amount_sar, { type: "number" }), field(text("refund_ar"), "deposit_refund_ar", deposit.refund_ar, { kind: "textarea" }), field(text("refund_en"), "deposit_refund_en", deposit.refund_en, { kind: "textarea" }), field(text("longRoute"), "long_stay_route", value.long_stay_route));
    const hours = node("fieldset", { className: "settings-group span-all" }); hours.appendChild(node("legend", { text: text("workingHours") })); DAYS.forEach(function (day) { const item = schedule(value, day), row = node("div", { className: "schedule-row" }); row.dataset.day = day; add(row, check(translatedDay(day, state.lang), "schedule." + day + ".enabled", item.enabled), field(text("from"), "schedule." + day + ".start", item.start, { type: "time" }), field(text("to"), "schedule." + day + ".end", item.end, { type: "time" })); hours.appendChild(row); }); form.appendChild(hours);
    const payments = node("fieldset", { className: "settings-group span-all", id: "payment-methods" }); payments.appendChild(node("legend", { text: state.lang === "ar" ? "طرق الدفع المعتمدة" : "Approved payment methods" })); const methods = commercial.payment_methods && commercial.payment_methods.length ? commercial.payment_methods : [{ ar: "", en: "" }];
    methods.forEach(function (method, index) { const row = node("div", { className: "payment-row" }); row.dataset.index = index; add(row, field(text("payment_ar"), "payment_methods." + index + ".ar", method.ar), field(text("payment_en"), "payment_methods." + index + ".en", method.en)); payments.appendChild(row); });
    const addPayment = node("button", { type: "button", className: "button button-secondary", text: text("addPayment") }); addPayment.addEventListener("click", function () { const index = payments.querySelectorAll(".payment-row").length, row = node("div", { className: "payment-row" }); row.dataset.index = index; add(row, field(text("payment_ar"), "payment_methods." + index + ".ar", ""), field(text("payment_en"), "payment_methods." + index + ".en", "")); payments.insertBefore(row, addPayment); }); payments.appendChild(addPayment); form.appendChild(payments); root.appendChild(form);
  }
  function settingsValue() {
    const form = id("global-form"), dayValues = {}, methods = [];
    DAYS.forEach(function (day) { dayValues[day] = { enabled: form.elements["schedule." + day + ".enabled"].checked, start: form.elements["schedule." + day + ".start"].value, end: form.elements["schedule." + day + ".end"].value }; });
    id("payment-methods").querySelectorAll(".payment-row").forEach(function (row) { const index = row.dataset.index; methods.push({ ar: form.elements["payment_methods." + index + ".ar"].value, en: form.elements["payment_methods." + index + ".en"].value }); });
    return buildSettingsPayload({ whatsapp_number: form.elements.whatsapp_number.value, timezone: form.elements.timezone.value, schedule: dayValues, internet_included: form.elements.internet_included.checked, maintenance_included: form.elements.maintenance_included.checked, deposit_amount_sar: form.elements.deposit_amount_sar.value, deposit_refund_ar: form.elements.deposit_refund_ar.value, deposit_refund_en: form.elements.deposit_refund_en.value, payment_methods: methods, long_stay_route: form.elements.long_stay_route.value });
  }
  async function loadSettings() { state.settings = await api("/api/monthly/ops/settings"); renderSettings(); }
  async function recoverSettingsConflict(error, localDraft) {
    if (error.status !== 409) return false;
    try { state.settings = retainConflictDraft(await api("/api/monthly/ops/settings"), localDraft); renderSettings(); }
    catch (_reloadError) { return false; }
    return true;
  }
  async function saveSettings() {
    const localDraft = settingsValue();
    try {
      const saved = await api("/api/monthly/ops/settings/draft", { method: "POST", body: JSON.stringify({ revision: state.settings.draft_revision, settings: localDraft }) });
      state.settings.draft_revision = saved.draft_revision; clearEditorConflict(id("settings-status")); id("settings-status").textContent = text("settingsSaved"); return saved;
    } catch (error) { await recoverSettingsConflict(error, localDraft); throw error; }
  }

  function renderPlaces() {
    const root = id("places-list"), keys = Object.keys(state.places || {}).sort(); renderPlacesSummary(); empty(root); if (!keys.length) { root.appendChild(node("p", { className: "empty-row", text: text("noPlaces") })); return; }
    keys.forEach(function (key) {
      const row = state.places[key], value = row.approved || row.draft || {}, item = node("article", { className: "place-row" }), main = node("div", { className: "place-row-main" }), actions = node("div", { className: "place-row-actions" }), button = node("button", { type: "button", className: "button button-secondary", text: text("edit") });
      button.addEventListener("click", function () { editPlace(key); });
      const category = value[state.lang === "ar" ? "category_ar" : "category_en"] || text(value.category_id);
      const cadence = value[state.lang === "ar" ? "review_interval_ar" : "review_interval_en"];
      add(main, node("strong", { text: value[state.lang === "ar" ? "label_ar" : "label_en"] || key }), node("p", { text: [category, (value.purposes || []).map(text).join(" · ")].filter(Boolean).join(" · ") }), node("span", { className: "place-meta", text: [value.verified_at ? text("verifiedOn") + " " + value.verified_at : "", cadence ? text("reviewEvery") + ": " + cadence : ""].filter(Boolean).join(" · ") }));
      add(actions, node("span", { className: "status-chip " + (row.active && row.approved ? "ready" : "warning"), text: row.active && row.approved ? text("ready") : text("review") }), button);
      add(item, main, actions); root.appendChild(item);
    });
  }
  function renderPlacesSummary() {
    const root = id("places-summary"), summary = summarizePlaces(state.places); empty(root);
    root.appendChild(node("strong", { text: summary.total + " " + text("approvedDestinations") }));
    PLACE_CATEGORIES.forEach(function (category) {
      if (!summary.categories[category]) return;
      root.appendChild(node("span", { className: "place-category-count", text: text(category) + ": " + summary.categories[category] }));
    });
  }
  function editPlace(key) {
    const row = key ? state.places[key] : null, value = clone(row && (row.draft || row.approved) || {}), root = id("place-fields"), form = grid(); state.placeId = key || ""; state.placeRevision = row ? row.draft_revision : 0; empty(root);
    if (present(value.lat) && present(value.lng)) value.coordinates = value.lat + "," + value.lng;
    add(form, field(text("place_id"), "place_id", key || "", { readOnly: Boolean(key) }), field(text("place_ar"), "label_ar", value.label_ar), field(text("place_en"), "label_en", value.label_en), field(text("place_coordinates"), "coordinates", value.coordinates, { full: true }), field(text("source_note"), "source_note", value.source_note, { kind: "textarea", full: true }));
    const purposes = node("fieldset", { className: "settings-group span-all" }); purposes.appendChild(node("legend", { text: text("purposes") })); PURPOSES.forEach(function (purpose) { purposes.appendChild(check(text(purpose), "purpose." + purpose, (value.purposes || []).includes(purpose))); }); form.appendChild(purposes); form.appendChild(check(text("activePlace"), "active", row ? row.active : true)); root.appendChild(form); id("place-form").hidden = false;
  }
  function placeValue() { const form = id("place-form"); return { id: form.elements.place_id.value.trim(), active: form.elements.active.checked, place: buildPlacePayload({ label_ar: form.elements.label_ar.value, label_en: form.elements.label_en.value, coordinates: form.elements.coordinates.value, source_note: form.elements.source_note.value, purposes: PURPOSES.filter(function (purpose) { return form.elements["purpose." + purpose].checked; }) }) }; }
  async function loadPlaces() { const result = await api("/api/monthly/ops/places"); state.places = result.places || {}; renderPlaces(); }
  async function recoverPlaceConflict(error, localValue) {
    if (error.status !== 409) return false;
    try {
      const latest = await api("/api/monthly/ops/places");
      state.places = latest.places || {};
      const row = state.places[localValue.id] || { draft_revision: 0, approved_revision: 0 };
      state.places[localValue.id] = Object.assign(retainConflictDraft(row, localValue.place), { active: localValue.active });
      renderPlaces(); editPlace(localValue.id);
    } catch (_reloadError) { return false; }
    return true;
  }
  async function savePlace() {
    const value = placeValue();
    try {
      const saved = await api("/api/monthly/ops/places/draft", { method: "POST", body: JSON.stringify({ place_id: value.id, revision: state.placeRevision, place: value.place }) });
      state.placeId = value.id; state.placeRevision = saved.draft_revision; clearEditorConflict(id("places-title")); id("places-title").textContent = text("placeSaved"); await loadPlaces(); return saved;
    } catch (error) { await recoverPlaceConflict(error, value); throw error; }
  }

  function bind() {
    id("catalog-ops-link").href = authPath("/monthly/ops", window.location.search); id("catalog-dashboard-link").href = authPath("/dashboard", window.location.search);
    id("catalog-language").addEventListener("click", function () { state.lang = state.lang === "ar" ? "en" : "ar"; applyCopy(); renderSummary(); renderRows(); if (state.listing && !id("survey").hidden) renderSurvey(); if (state.settings && !id("global-setup").hidden) renderSettings(); if (!id("places").hidden) renderPlaces(); });
    document.querySelectorAll(".workspace-tab").forEach(function (tab) { tab.addEventListener("click", async function () { const panel = tab.dataset.panel; show(panel); try { if (panel === "global-setup" && !state.settings) await loadSettings(); if (panel === "places") await loadPlaces(); } catch (error) { globalError(error); } }); });
    ["listing-search", "status-filter", "blocker-filter"].forEach(function (key) { id(key).addEventListener("input", renderRows); id(key).addEventListener("change", renderRows); }); id("portfolio-filters").addEventListener("submit", function (event) { event.preventDefault(); renderRows(); });
    id("close-survey").addEventListener("click", function () { show("portfolio"); }); id("survey-form").addEventListener("submit", function (event) { event.preventDefault(); saveProfile(false).catch(function () {}); }); id("preview-profile").addEventListener("click", function () { saveProfile(true).catch(function () {}); }); id("approve-profile").addEventListener("click", approveProfile);
    id("global-form").addEventListener("submit", function (event) { event.preventDefault(); saveSettings().catch(function (error) { editorError(id("settings-status"), error, state.settings); }); });
    id("approve-settings").addEventListener("click", async function () { try { const saved = await saveSettings(); await api("/api/monthly/ops/settings/approve", { method: "POST", body: JSON.stringify({ revision: saved.draft_revision }) }); id("settings-status").textContent = text("settingsApproved"); await loadSettings(); await loadRows(); } catch (error) { editorError(id("settings-status"), error, state.settings); } });
    id("new-place").addEventListener("click", function () { editPlace(null); }); id("place-form").addEventListener("submit", function (event) { event.preventDefault(); savePlace().catch(function (error) { editorError(id("places-title"), error, state.places[state.placeId]); }); });
    id("approve-place").addEventListener("click", async function () { try { const saved = await savePlace(), value = placeValue(); await api("/api/monthly/ops/places/approve", { method: "POST", body: JSON.stringify({ place_id: state.placeId, revision: saved.draft_revision, active: value.active }) }); id("places-title").textContent = text("placeApproved"); await loadPlaces(); id("place-form").hidden = true; } catch (error) { editorError(id("places-title"), error, state.places[state.placeId]); } });
    id("refresh-catalog").addEventListener("click", async function () { const button = id("refresh-catalog"); button.disabled = true; try { await api("/api/monthly/ops/refresh", { method: "POST", body: JSON.stringify({}) }); button.textContent = text("refreshOk"); await loadRows(); } catch (error) { globalError(error); } finally { button.disabled = false; } });
  }

  applyCopy(); bind();
  loadRows().then(function () {
    document.documentElement.dataset.catalogReady = "complete";
    const params = new URLSearchParams(window.location.search);
    const listingId = params.get("id"), requestedSection = params.get("section");
    if (listingId && /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(listingId)) {
      if (requestedSection && STEPS.includes(requestedSection)) state.step = requestedSection;
      openListing(listingId).then(function () {
        if (requestedSection && STEPS.includes(requestedSection)) { state.step = requestedSection; renderSurvey(); }
      });
    }
  }).catch(function (error) { document.documentElement.dataset.catalogReady = "error"; globalError(error); });
}());
