(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.OujaMonthly = api;
  }
  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", api.boot, { once: true });
  }
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  const COPY = {
    ar: {
      brand: "عوجا بالشهر",
      brandHome: "عوجا بالشهر، الرئيسية",
      pageTitle: "عوجا بالشهر · الرياض",
      primaryNav: "التنقل الرئيسي",
      browseNav: "تصفح البيوت",
      switchLanguage: "Switch to English",
      switchLabel: "English",
      skip: "انتقل إلى المحتوى",
      footer: "عوجا ريزدنس · إقامة شهرية مُدارة في الرياض",
      eyebrow: "OUJA MONTHLY · RIYADH",
      heroTitle: "بيتك في الرياض، جاهز من أول يوم.",
      heroIntro: "شقق مفروشة مختارة للإقامة الشهرية، بسعر واضح، دخول مرن، ودعم عوجا طوال إقامتك.",
      guidedCta: "ساعدني أختار الأنسب",
      browseCta: "تصفح البيوت",
      browseCount: "تصفح {count} بيتًا",
      browseRounded: "تصفح أكثر من {count} بيتًا",
      proofManaged: "إدارة ودعم من عوجا",
      proofManagedText: "فريق واحد يساعدك قبل السكن وخلال الإقامة.",
      proofPrice: "سعر شهري رسمي",
      proofPriceText: "نعرض السعر والتفاصيل بعد اختيار التواريخ.",
      proofPrivacy: "اختيار بدون بيانات شخصية",
      proofPrivacyText: "ما نطلب رقم هاتف قبل ما تشوف النتائج.",
      catalogPreview: "بيوت جاهزة للإقامة الشهرية",
      catalogPreviewText: "كل بيت هنا يمر على فحص النشر قبل ظهوره.",
      viewCatalog: "اعرض كل البيوت",
      loading: "جاري تجهيز الخيارات المتاحة.",
      retry: "حاول مرة ثانية",
      serviceUnavailable: "تعذر تحميل خدمة السكن الشهري حاليًا.",
      serviceUnavailableHelp: "جرّب مرة ثانية بعد قليل. ما راح نعرض توفرًا أو سعرًا غير مؤكد.",
      partialService: "بعض خدمات التواصل غير جاهزة حاليًا، ويظل تصفح البيوت متاحًا.",
      startOver: "ابدأ من جديد",
      back: "رجوع",
      progress: "الخطوة {current} من {total}",
      purposeTitle: "وش سبب إقامتك في الرياض؟",
      purposeHint: "نستخدم إجابتك عشان نرتب البيوت حسب احتياجك الفعلي.",
      work: "عمل أو انتقال وظيفي",
      family: "سكن عائلي مؤقت",
      treatment: "علاج",
      visit: "زيارة أو مناسبة",
      placeTitleWork: "وش المكان المهم لدوامك؟",
      placeTitleTreatment: "وش المستشفى أو الوجهة الطبية المهمة؟",
      placeTitleVisit: "وش مكان الزيارة أو المناسبة؟",
      placeHint: "نعرض القرب فقط إذا كانت بيانات الموقع موثقة.",
      placeUnavailable: "ما فيه وجهة معتمدة لهذا المسار حاليًا.",
      residentsTitle: "كم شخص بيسكن؟",
      residentsHint: "نستبعد أي بيت سعته الموثقة أقل من عدد المقيمين.",
      residentsCustom: "عدد آخر",
      residentsLabel: "عدد المقيمين",
      sleepingTitle: "وش ترتيب النوم المناسب لكم؟",
      sleepingHint: "اختر الحد الأدنى المناسب، أو خلّ الترتيب مرن.",
      studio: "استديو",
      oneBedroom: "غرفة نوم واحدة",
      twoBedrooms: "غرفتا نوم",
      threeBedrooms: "ثلاث غرف نوم",
      fourBedrooms: "أربع غرف أو أكثر",
      separateBeds: "أسرة منفصلة للمقيمين",
      flexibleSleeping: "مرن",
      datesTitle: "متى تبدأ الإقامة وكم مدتها؟",
      datesHint: "اختر مدة بالأشهر أو تاريخ خروج محدد، ثم اضغط متابعة.",
      moveIn: "تاريخ الدخول",
      durationChoice: "مدة بالأشهر",
      departureChoice: "تاريخ خروج محدد",
      duration: "مدة الإقامة",
      monthOne: "شهر واحد",
      monthsCount: "{count} أشهر",
      moveOut: "تاريخ الخروج",
      continue: "متابعة",
      datesRequired: "حدد تاريخ الدخول والمدة أو تاريخ الخروج الصحيح.",
      flexibilityTitle: "هل تواريخك ثابتة؟",
      flexibilityHint: "إذا اخترت المرونة، نبحث ضمن سبعة أيام قبل أو بعد تاريخك.",
      fixedDates: "تواريخ ثابتة",
      flexibleDates: "مرونة 7 أيام قبل أو بعد",
      matching: "نرتب البيوت المناسبة حسب التوفر والملاءمة.",
      resultsTitle: "خيارات مناسبة لإقامتك",
      bestThree: "أفضل 3 لك",
      bestThreeText: "مرتبة حسب التوفر والاحتياج الذي اخترته.",
      strongOptions: "خيارات قوية أخرى",
      allAvailable: "كل الشقق المتاحة",
      nearMatches: "أقرب خيارات موثقة",
      whyFits: "ليش تناسبك",
      whyRecommended: "لماذا رشحناها لك؟",
      tradeoff: "نقطة تستحق الانتباه",
      quoteIncludes: "يشمل {items}",
      adjustedDates: "التواريخ المتاحة: {moveIn} إلى {moveOut}",
      viewHome: "اعرض تفاصيل البيت",
      noExact: "ما لقينا تطابقًا كاملًا للتفاصيل المحددة.",
      nearHelp: "هذي الخيارات تغيّر شرطًا واحدًا بشكل واضح، بدون افتراض توفر غير موثق.",
      pendingAvailability: "بيوت قيد تأكيد التوفر: {count}",
      unavailableCount: "بيوت غير متاحة للتواريخ: {count}",
      missingPriceCount: "بيوت بدون سعر رسمي للتواريخ: {count}",
      browseTitle: "كل البيوت الشهرية المؤهلة",
      browseIntro: "العدد والخيارات محسوبة من البيوت التي اجتازت فحص النشر.",
      filtersTitle: "فلتر البيوت",
      residentsOptional: "عدد المقيمين",
      bedrooms: "غرف النوم",
      allBedrooms: "كل أحجام البيوت",
      neighborhood: "الحي",
      allNeighborhoods: "كل الأحياء",
      importantPlace: "مكان مهم",
      allPlaces: "كل الأماكن المعتمدة",
      applyFilters: "اعرض النتائج",
      clearFilters: "مسح الفلاتر",
      homesCount: "{count} بيتًا",
      noBrowseResults: "ما فيه بيت منشور يطابق هذي الفلاتر حاليًا.",
      pendingBrowse: "بعض البيوت مستبعدة لأن التوفر ما زال قيد التأكيد.",
      available: "متاح للتواريخ المحددة",
      pending: "التوفر قيد التأكيد",
      unavailable: "غير متاح للتواريخ المحددة",
      bedroomsFact: "{count} غرف نوم",
      studioFact: "استديو",
      bathroomsFact: "{count} دورات مياه",
      capacityFact: "يسع {count}",
      areaFact: "{count} م²",
      bedsFact: "{count} أسرّة",
      rating: "{rating} من 5 · {count} مراجعة",
      perMonth: "{amount} ر.س شهريًا",
      listingNotFound: "هذا البيت غير موجود ضمن الكتالوج المنشور.",
      homeFacts: "تفاصيل البيت",
      story: "عن البيت",
      amenities: "المرافق الموثقة",
      location: "الموقع",
      licence: "بيانات الإعلان",
      licenceNumber: "رقم الترخيص: {value}",
      licenceExpiry: "ساري حتى: {value}",
      priceTitle: "السعر والتفاصيل",
      chooseDatesForPrice: "حدد تفاصيل الإقامة لعرض السعر الرسمي.",
      getOfficialPrice: "اعرض السعر الرسمي",
      quotePending: "التوفر قيد التأكيد لهذه التواريخ.",
      quoteUnavailable: "البيت غير متاح للتواريخ المحددة.",
      quoteMissing: "السعر الرسمي غير متاح للتواريخ المحددة.",
      monthlyRate: "السعر الشهري",
      stayTotal: "إجمالي الإقامة",
      included: "المشمول",
      internet: "الإنترنت",
      maintenance: "الصيانة",
      utilities: "الخدمات والفواتير",
      cleaning: "التنظيف",
      deposit: "التأمين والاسترداد",
      paymentMethods: "طرق الدفع",
      contactWhatsApp: "جهّز طلب واتساب",
      contactBlocked: "التواصل عبر واتساب غير جاهز حاليًا. تقدر تكمل تصفح البيوت والأسعار.",
      secureSessionBlocked: "تعذر تجهيز جلسة آمنة لطلب واتساب حاليًا. أعد تحميل الصفحة أو أكمل تصفح البيوت.",
      completeDetails: "أكمل تفاصيل الإقامة لتجهيز طلب واتساب.",
      preparingWhatsApp: "جاري تجهيز مرجع الطلب ورسالة واتساب.",
      openingWhatsApp: "تم إنشاء المرجع {reference}. جاري فتح واتساب، والرسالة لن تُرسل إلا باختيارك.",
      leadFailed: "تعذر تجهيز طلب واتساب بشكل آمن.",
      generalHelpTitle: "خلّ فريق عوجا يساعدك",
      generalHelpText: "ما راح نختار بيتًا أو ندّعي توفرًا. نرسل تفاصيل بحثك فقط عشان يساعدك الفريق في إيجاد خيار وتأكيده.",
      generalHelpAction: "جهّز طلب مساعدة",
      selectPurpose: "سبب الإقامة",
      selectSleeping: "ترتيب النوم",
      selectFlexibility: "مرونة التواريخ"
    },
    en: {
      brand: "Ouja Monthly",
      brandHome: "Ouja Monthly, home",
      pageTitle: "Ouja Monthly · Riyadh",
      primaryNav: "Primary navigation",
      browseNav: "Browse homes",
      switchLanguage: "التبديل إلى العربية",
      switchLabel: "العربية",
      skip: "Skip to content",
      footer: "Ouja Residence · Managed monthly stays in Riyadh",
      eyebrow: "OUJA MONTHLY · RIYADH",
      heroTitle: "Your Riyadh home, ready from day one.",
      heroIntro: "Selected furnished homes for monthly stays, with clear pricing, flexible arrival, and Ouja support throughout your stay.",
      guidedCta: "Help me choose",
      browseCta: "Browse homes",
      browseCount: "Browse {count} homes",
      browseRounded: "Browse {count}+ homes",
      proofManaged: "Managed and supported by Ouja",
      proofManagedText: "One team helps before move-in and throughout your stay.",
      proofPrice: "One official monthly price",
      proofPriceText: "See the rate and terms after selecting your dates.",
      proofPrivacy: "Choose without personal details",
      proofPrivacyText: "No phone number is requested before you see results.",
      catalogPreview: "Homes prepared for monthly stays",
      catalogPreviewText: "Every home shown here passes publication checks.",
      viewCatalog: "View all homes",
      loading: "Preparing the available options.",
      retry: "Try again",
      serviceUnavailable: "The monthly-stay service could not load right now.",
      serviceUnavailableHelp: "Try again shortly. We will not show unconfirmed availability or pricing.",
      partialService: "Some contact services are not ready, but browsing remains available.",
      startOver: "Start again",
      back: "Back",
      progress: "Step {current} of {total}",
      purposeTitle: "What brings you to Riyadh?",
      purposeHint: "Your answer helps us rank homes for your actual stay needs.",
      work: "Work or relocation",
      family: "Temporary family home",
      treatment: "Treatment",
      visit: "Visit or event",
      placeTitleWork: "Which place matters for your work?",
      placeTitleTreatment: "Which hospital or medical destination matters?",
      placeTitleVisit: "Which venue or place matters for your visit?",
      placeHint: "We only show proximity when location data is verified.",
      placeUnavailable: "No approved destination is available for this route yet.",
      residentsTitle: "How many people will stay?",
      residentsHint: "Homes with a lower verified capacity are excluded.",
      residentsCustom: "Another number",
      residentsLabel: "Number of residents",
      sleepingTitle: "Which sleeping arrangement do you need?",
      sleepingHint: "Choose the minimum that works, or keep the arrangement flexible.",
      studio: "Studio",
      oneBedroom: "One bedroom",
      twoBedrooms: "Two bedrooms",
      threeBedrooms: "Three bedrooms",
      fourBedrooms: "Four or more bedrooms",
      separateBeds: "Separate beds for residents",
      flexibleSleeping: "Flexible",
      datesTitle: "When will you arrive and how long will you stay?",
      datesHint: "Choose a month duration or an exact move-out date, then continue.",
      moveIn: "Move-in date",
      durationChoice: "Duration in months",
      departureChoice: "Exact move-out date",
      duration: "Stay duration",
      monthOne: "One month",
      monthsCount: "{count} months",
      moveOut: "Move-out date",
      continue: "Continue",
      datesRequired: "Choose a valid move-in date and duration or move-out date.",
      flexibilityTitle: "Are your dates fixed?",
      flexibilityHint: "With flexibility, we can look seven days before or after your date.",
      fixedDates: "Fixed dates",
      flexibleDates: "Seven days before or after",
      matching: "Ranking suitable homes by verified availability and fit.",
      resultsTitle: "Homes suited to your stay",
      bestThree: "Your best three",
      bestThreeText: "Ranked by availability and the needs you selected.",
      strongOptions: "Other strong options",
      allAvailable: "All available homes",
      nearMatches: "Closest verified options",
      whyFits: "Why it fits",
      whyRecommended: "Why we recommended it",
      tradeoff: "A useful trade-off",
      quoteIncludes: "Includes {items}",
      adjustedDates: "Available dates: {moveIn} to {moveOut}",
      viewHome: "View home details",
      noExact: "No exact match was found for the selected details.",
      nearHelp: "These options clearly change one condition without assuming unverified availability.",
      pendingAvailability: "Homes awaiting availability confirmation: {count}",
      unavailableCount: "Homes unavailable for these dates: {count}",
      missingPriceCount: "Homes without an official rate for these dates: {count}",
      browseTitle: "All eligible monthly homes",
      browseIntro: "The count and options come only from homes that passed publication checks.",
      filtersTitle: "Filter homes",
      residentsOptional: "Residents",
      bedrooms: "Bedrooms",
      allBedrooms: "All home sizes",
      neighborhood: "Neighborhood",
      allNeighborhoods: "All neighborhoods",
      importantPlace: "Important place",
      allPlaces: "All approved places",
      applyFilters: "Show results",
      clearFilters: "Clear filters",
      homesCount: "{count} homes",
      noBrowseResults: "No published home matches these filters right now.",
      pendingBrowse: "Some homes are excluded while availability is being confirmed.",
      available: "Available for selected dates",
      pending: "Availability being confirmed",
      unavailable: "Unavailable for selected dates",
      bedroomsFact: "{count} bedrooms",
      studioFact: "Studio",
      bathroomsFact: "{count} bathrooms",
      capacityFact: "Sleeps {count}",
      areaFact: "{count} m²",
      bedsFact: "{count} beds",
      rating: "{rating} out of 5 · {count} reviews",
      perMonth: "SAR {amount} per month",
      listingNotFound: "This home is not in the published catalog.",
      homeFacts: "Home details",
      story: "About this home",
      amenities: "Verified amenities",
      location: "Location",
      licence: "Advertising information",
      licenceNumber: "Licence number: {value}",
      licenceExpiry: "Valid until: {value}",
      priceTitle: "Price and terms",
      chooseDatesForPrice: "Select your stay details to see the official price.",
      getOfficialPrice: "Show official price",
      quotePending: "Availability is being confirmed for these dates.",
      quoteUnavailable: "The home is unavailable for the selected dates.",
      quoteMissing: "The official price is unavailable for the selected dates.",
      monthlyRate: "Monthly rate",
      stayTotal: "Stay total",
      included: "Included",
      internet: "Internet",
      maintenance: "Maintenance",
      utilities: "Utilities",
      cleaning: "Cleaning",
      deposit: "Deposit and refund",
      paymentMethods: "Payment methods",
      contactWhatsApp: "Prepare WhatsApp request",
      contactBlocked: "WhatsApp contact is not ready. You can still browse homes and prices.",
      secureSessionBlocked: "A secure request session is unavailable. Reload the page or continue browsing homes.",
      completeDetails: "Complete the stay details to prepare a WhatsApp request.",
      preparingWhatsApp: "Creating your lead reference and WhatsApp message.",
      openingWhatsApp: "Reference {reference} created. Opening WhatsApp; the message is sent only if you choose to send it.",
      leadFailed: "The WhatsApp request could not be prepared safely.",
      generalHelpTitle: "Ask the Ouja team for help",
      generalHelpText: "No home will be selected and no availability will be assumed. We only send your search details so the team can find and confirm an option.",
      generalHelpAction: "Prepare help request",
      selectPurpose: "Stay purpose",
      selectSleeping: "Sleeping arrangement",
      selectFlexibility: "Date flexibility"
    }
  };

  const PURPOSE_KEYS = ["work", "family", "treatment", "visit"];
  const SLEEPING = [
    ["studio", "studio"],
    ["one_bedroom", "oneBedroom"],
    ["two_bedrooms", "twoBedrooms"],
    ["three_bedrooms", "threeBedrooms"],
    ["four_plus_bedrooms", "fourBedrooms"],
    ["separate_beds", "separateBeds"],
    ["flexible", "flexibleSleeping"]
  ];
  const STORAGE_KEY = "ouja_monthly_anonymous_state_v2";
  const SESSION_TOKEN_RE = /^anon_[A-Za-z0-9_-]{32}\.[A-Za-z0-9_-]{43}$/;
  const SAFE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
  const ENDPOINTS = {
    config: "/api/monthly/config",
    browse: "/api/monthly/search",
    match: "/api/monthly/match",
    lead: "/api/monthly/lead",
    event: "/api/monthly/event"
  };

  const runtime = {
    lang: "ar",
    page: { route: "home", slug: null, listing_id: null },
    config: null,
    matcher: null,
    request: null,
    listingRequest: {},
    recommendationContext: null,
    impressedListingIds: new Set(),
    results: null,
    currentListing: null,
    quote: null,
    browseQuery: {},
    booted: false
  };

  function copy(key, values) {
    let value = (COPY[runtime.lang] && COPY[runtime.lang][key]) || COPY.ar[key] || key;
    Object.keys(values || {}).forEach(function (name) {
      value = value.replace("{" + name + "}", String(values[name]));
    });
    return value;
  }

  function safeImageUrl(value) {
    if (typeof value !== "string") return "";
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
    } catch (_error) {
      return "";
    }
  }

  function safeWhatsAppUrl(value) {
    if (typeof value !== "string") return "";
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" && parsed.hostname === "wa.me" ? parsed.href : "";
    } catch (_error) {
      return "";
    }
  }

  function approvedIncluded(values) {
    if (!Array.isArray(values)) return [];
    return ["internet", "maintenance"].filter(function (key) { return values.indexOf(key) !== -1; });
  }

  function validSessionToken(value) {
    return typeof value === "string" && SESSION_TOKEN_RE.test(value);
  }

  function chooseSessionToken(existing, issued) {
    if (validSessionToken(existing)) return existing;
    return validSessionToken(issued) ? issued : null;
  }

  function responseWindowMessage(source, lang) {
    if (!source || typeof source !== "object") return "";
    const windowValue = source.response_window && typeof source.response_window === "object" ? source.response_window : source;
    const value = windowValue[lang === "en" ? "message_en" : "message_ar"];
    return typeof value === "string" ? value.trim() : "";
  }

  function contactState(config, lang) {
    const language = lang === "en" ? "en" : "ar";
    const value = config && typeof config === "object" ? config : {};
    const blockers = Array.isArray(value.blockers) ? value.blockers : [];
    if (blockers.some(function (item) { return item && item.field === "whatsapp_number"; })) {
      return { disabled: true, message: COPY[language].contactBlocked, response_message: "" };
    }
    if (!validSessionToken(value.session_id)) {
      return { disabled: true, message: COPY[language].secureSessionBlocked, response_message: "" };
    }
    return { disabled: false, message: "", response_message: responseWindowMessage(value, language) };
  }

  function validDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const parsed = new Date(value + "T00:00:00Z");
    return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }

  function adjustedDateWindow(item) {
    if (!item || item.changed_condition !== "dates") return null;
    const moveIn = item.adjusted_move_in;
    const moveOut = item.adjusted_move_out;
    if (!validDate(moveIn) || !validDate(moveOut) || moveOut <= moveIn) return null;
    return { move_in: moveIn, move_out: moveOut };
  }

  function canonicalListingRequest(request, item) {
    const value = request && typeof request === "object" ? Object.assign({}, request) : {};
    const adjusted = adjustedDateWindow(item);
    if (adjusted) {
      value.move_in = adjusted.move_in;
      if (validDate(value.move_out)) {
        value.move_out = adjusted.move_out;
        delete value.duration_months;
      } else {
        delete value.move_out;
      }
    }
    return value;
  }

  async function retrySessionOperation(operation, current, _cachedFresh, refresh, onRotate) {
    try {
      return await operation(current);
    } catch (error) {
      if (!error || error.code !== "invalid_signature" || typeof refresh !== "function") throw error;
      const replacement = await refresh();
      if (!validSessionToken(replacement) || replacement === current) throw error;
      if (typeof onRotate === "function") onRotate(replacement);
      return operation(replacement);
    }
  }

  function boundedInteger(value, minimum, maximum) {
    if (typeof value !== "string" || !/^\d+$/.test(value)) return null;
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
  }

  function parseLocationSearch(search, route) {
    const values = {};
    const params = new URLSearchParams(typeof search === "string" ? search : "");
    const moveIn = params.get("move_in");
    const moveOut = params.get("move_out");
    const months = boundedInteger(params.get("duration_months") || params.get("months"), 1, 6);
    const residents = boundedInteger(params.get("residents") || params.get("guests"), 1, 50);
    const rawBedrooms = params.get("bedrooms") || params.get("beds");
    const bedrooms = rawBedrooms === "studio" ? 0 : boundedInteger(rawBedrooms, 0, 20);
    if (validDate(moveIn)) values.move_in = moveIn;
    if (validDate(moveOut) && values.move_in && moveOut > values.move_in) values.move_out = moveOut;
    else if (months !== null) values.duration_months = months;
    if (residents !== null) values.residents = residents;
    if (bedrooms !== null) values.bedrooms = bedrooms;
    const neighborhood = params.get("neighborhood");
    if (neighborhood && SAFE_ID_RE.test(neighborhood)) values.neighborhood = neighborhood;
    const placeValue = params.get("place");
    if (placeValue) {
      try {
        const place = JSON.parse(placeValue);
        if (place && ["destination", "neighborhood"].indexOf(place.kind) !== -1 && SAFE_ID_RE.test(place.id || "") && typeof place.label === "string" && place.label.length > 0 && place.label.length <= 120) {
          values.place = { kind: place.kind, id: place.id, label: place.label };
        }
      } catch (_error) {
        /* Invalid URL state is ignored rather than sent to the API. */
      }
    }
    if (route === "listing") {
      const purpose = params.get("purpose");
      const sleeping = params.get("sleeping");
      const flexibility = params.get("flexibility");
      if (PURPOSE_KEYS.indexOf(purpose) !== -1) values.purpose = purpose;
      if (SLEEPING.some(function (row) { return row[0] === sleeping; })) values.sleeping = sleeping;
      if (["fixed", "plus_minus_7"].indexOf(flexibility) !== -1) values.flexibility = flexibility;
    }
    return values;
  }

  function publicAvailabilityStatus(value, hasDates) {
    if (!hasDates) return "";
    return ["available", "pending", "unavailable"].indexOf(value) !== -1 ? value : "";
  }

  function rankedImpressionIds(result) {
    const seen = {};
    return [].concat(result && result.top || [], result && result.near_matches || [], result && result.alternatives || []).reduce(function (ids, item) {
      const id = item && item.id !== undefined ? String(item.id) : "";
      if (id && !seen[id]) {
        seen[id] = true;
        ids.push(id);
      }
      return ids;
    }, []);
  }

  function optionIsSelected(selected, value) {
    if (selected === undefined || selected === null) return String(value) === "";
    return String(selected) === String(value);
  }

  function safeRecommendationContext(item, lang) {
    const rawId = item && item.id !== undefined ? item.id : item && item.listing_id;
    const listingId = rawId !== undefined ? String(rawId) : "";
    if (!SAFE_ID_RE.test(listingId)) return null;
    const reasons = (Array.isArray(item.reasons) ? item.reasons : []).filter(function (reason) {
      return typeof reason === "string" && reason.trim().length > 0 && reason.trim().length <= 300;
    }).slice(0, 4).map(function (reason) { return reason.trim(); });
    const tradeoff = typeof item.tradeoff === "string" && item.tradeoff.trim().length <= 300 ? item.tradeoff.trim() : "";
    if (!reasons.length && !tradeoff) return null;
    const slug = typeof item.slug === "string" && SAFE_ID_RE.test(item.slug) ? item.slug : null;
    return { listing_id: listingId, slug: slug, lang: lang === "en" ? "en" : "ar", reasons: reasons, tradeoff: tradeoff };
  }

  function buildSteps(answers) {
    const steps = ["purpose"];
    if (["work", "treatment", "visit"].indexOf(answers && answers.purpose) !== -1) {
      steps.push("place");
    }
    return steps.concat(["residents", "sleeping", "dates", "flexibility"]);
  }

  function initialMatcherState(saved) {
    const answers = saved && typeof saved.answers === "object" && saved.answers ? Object.assign({}, saved.answers) : {};
    const steps = buildSteps(answers);
    const wanted = saved && Number.isInteger(saved.current) ? saved.current : 0;
    return { answers: answers, steps: steps, current: Math.max(0, Math.min(wanted, steps.length)) };
  }

  function clearStepAnswer(answers, step) {
    if (step === "dates") {
      ["date_mode", "move_in", "move_out", "duration_months"].forEach(function (key) { delete answers[key]; });
    } else {
      delete answers[step];
    }
  }

  function answerStep(state, step, value) {
    const priorSteps = state.steps.slice();
    const position = priorSteps.indexOf(step);
    if (position < 0) return state;
    const answers = Object.assign({}, state.answers);
    priorSteps.slice(position + 1).forEach(function (future) { clearStepAnswer(answers, future); });
    clearStepAnswer(answers, step);
    if (step === "dates") {
      answers.date_mode = value.date_mode;
      answers.move_in = value.move_in;
      if (value.date_mode === "departure") answers.move_out = value.move_out;
      else answers.duration_months = Number(value.duration_months);
    } else {
      answers[step] = value;
    }
    const steps = buildSteps(answers);
    const next = Math.min(steps.length, steps.indexOf(step) + 1);
    return { answers: answers, steps: steps, current: next };
  }

  function goBack(state) {
    return {
      answers: Object.assign({}, state.answers),
      steps: state.steps.slice(),
      current: Math.max(0, state.current - 1)
    };
  }

  function buildMatchRequest(answers) {
    const request = {
      purpose: answers.purpose,
      residents: Number(answers.residents),
      sleeping: answers.sleeping,
      move_in: answers.move_in,
      flexibility: answers.flexibility
    };
    if (answers.place) request.place = answers.place;
    if (answers.date_mode === "departure" && answers.move_out) request.move_out = answers.move_out;
    else if (answers.duration_months) request.duration_months = Number(answers.duration_months);
    return request;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function append(parent) {
    Array.prototype.slice.call(arguments, 1).forEach(function (child) {
      if (child) parent.appendChild(child);
    });
    return parent;
  }

  function svgIcon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    use.setAttribute("href", "#icon-" + name);
    svg.appendChild(use);
    return svg;
  }

  function button(label, className, handler) {
    const node = element("button", className, label);
    node.type = "button";
    if (handler) node.addEventListener("click", handler);
    return node;
  }

  function actionLink(label, href, className, handler) {
    const node = element("a", className, label);
    node.href = href;
    if (handler) node.addEventListener("click", handler);
    return node;
  }

  function announce(message, error) {
    const node = document.getElementById(error ? "monthly-errors" : "monthly-status");
    if (node) node.textContent = message || "";
  }

  function main() {
    return document.getElementById("monthly-main");
  }

  function clearMain() {
    const target = main();
    target.replaceChildren();
    return target;
  }

  function formatNumber(value) {
    try {
      return new Intl.NumberFormat(runtime.lang === "ar" ? "ar-SA" : "en-US", { maximumFractionDigits: 2 }).format(value);
    } catch (_error) {
      return String(value);
    }
  }

  function deviceClass() {
    if (typeof window === "undefined") return "unknown";
    if (window.innerWidth < 600) return "mobile";
    if (window.innerWidth < 1024) return "tablet";
    return "desktop";
  }

  function sessionPayload() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}");
    } catch (_error) {
      return {};
    }
  }

  function persistState() {
    if (typeof sessionStorage === "undefined") return;
    const state = {
      lang: runtime.lang,
      session_id: runtime.config && runtime.config.session_id,
      matcher: runtime.matcher,
      request: runtime.request,
      listing_request: runtime.listingRequest,
      recommendation_context: runtime.recommendationContext
    };
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (_error) {
      return;
    }
  }

  function queryString(values) {
    const params = new URLSearchParams();
    Object.keys(values || {}).forEach(function (key) {
      const value = values[key];
      if (value !== undefined && value !== null && value !== "") {
        params.set(key, typeof value === "object" ? JSON.stringify(value) : String(value));
      }
    });
    const output = params.toString();
    return output ? "?" + output : "";
  }

  async function requestJSON(path, options) {
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(function () { controller.abort(); }, 10000) : null;
    try {
      const response = await fetch(path, Object.assign({
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        signal: controller ? controller.signal : undefined
      }, options || {}));
      const data = await response.json();
      if (!response.ok || data.ok === false) {
        const details = data && data.error ? data.error : {};
        const message = details[runtime.lang === "ar" ? "message_ar" : "message_en"] || copy("serviceUnavailable");
        const failure = new Error(message);
        failure.code = details.code || "request_failed";
        failure.field = details.field || "request";
        failure.payload = data;
        throw failure;
      }
      return data;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  function getJSON(path, values) {
    return requestJSON(path + queryString(values));
  }

  function postJSON(path, value) {
    return requestJSON(path, {
      method: "POST",
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(value)
    });
  }

  async function mintFreshSessionToken() {
    const refreshed = await getJSON(ENDPOINTS.config, { lang: runtime.lang });
    const issued = refreshed && refreshed.session_id;
    if (!validSessionToken(issued)) return null;
    runtime.config = refreshed;
    return issued;
  }

  function withSessionRetry(operation) {
    const current = runtime.config && runtime.config.session_id;
    const fresh = runtime.config && runtime.config.fresh_session_id;
    return retrySessionOperation(operation, current, fresh, mintFreshSessionToken, function (replacement) {
      runtime.config.session_id = replacement;
      runtime.config.fresh_session_id = null;
      persistState();
    });
  }

  function safeEventContext(context) {
    return Object.assign({ language: runtime.lang, device_class: deviceClass() }, context || {});
  }

  function track(event, context) {
    const sessionId = runtime.config && runtime.config.session_id;
    if (!validSessionToken(sessionId)) return Promise.resolve(false);
    return withSessionRetry(function (activeSessionId) {
      return postJSON(ENDPOINTS.event, {
        event: event,
        session_id: activeSessionId,
        context: safeEventContext(context)
      });
    }).then(function () { return true; }).catch(function () { return false; });
  }

  function applyShellCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (node) {
      node.textContent = copy(node.getAttribute("data-copy"));
    });
    document.querySelectorAll("[data-copy-aria]").forEach(function (node) {
      node.setAttribute("aria-label", copy(node.getAttribute("data-copy-aria")));
    });
    const skip = document.querySelector(".skip-link");
    if (skip) skip.textContent = copy("skip");
    const brand = document.querySelector(".brand");
    if (brand) brand.setAttribute("aria-label", copy("brandHome"));
    document.title = copy("pageTitle");
    const languageButton = document.getElementById("language-switch");
    if (languageButton) {
      languageButton.textContent = copy("switchLabel");
      languageButton.setAttribute("aria-label", copy("switchLanguage"));
    }
  }

  async function setLanguage(lang) {
    runtime.lang = lang === "en" ? "en" : "ar";
    document.documentElement.lang = runtime.lang;
    document.documentElement.dir = runtime.lang === "ar" ? "rtl" : "ltr";
    applyShellCopy();
    persistState();
    await loadConfig();
    await loadRoute(false);
  }

  function focusMain() {
    const target = main();
    if (target) {
      target.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "auto" });
    }
  }

  function focusQuestion() {
    const target = document.querySelector('[data-view="question"] h1');
    if (target) {
      target.tabIndex = -1;
      target.focus({ preventScroll: true });
    }
  }

  function parsePageState() {
    const node = document.getElementById("monthly-page-state");
    if (!node) return { route: "home", slug: null, listing_id: null };
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (_error) {
      return { route: "home", slug: null, listing_id: null };
    }
  }

  function routeFromLocation() {
    const path = window.location.pathname;
    if (path === "/monthly" || path === "/monthly/") return { route: "home", slug: null, listing_id: null };
    if (path === "/monthly/match") return { route: "match", slug: null, listing_id: null };
    if (path === "/monthly/search") return { route: "browse", slug: null, listing_id: null };
    const idMatch = path.match(/^\/monthly\/id\/([A-Za-z0-9_-]+)$/);
    if (idMatch) return { route: "listing", listing_id: idMatch[1], slug: null };
    const slugMatch = path.match(/^\/monthly\/([A-Za-z0-9_-]+)$/);
    if (slugMatch) return { route: "listing", listing_id: null, slug: slugMatch[1] };
    return { route: "home", slug: null, listing_id: null };
  }

  function applyLocationSearch() {
    const parsed = parseLocationSearch(window.location.search, runtime.page.route);
    if (runtime.page.route === "browse") {
      runtime.browseQuery = parsed;
      runtime.request = null;
      runtime.matcher = initialMatcherState();
      runtime.results = null;
      runtime.recommendationContext = null;
      runtime.listingRequest = {};
      return;
    }
    if (runtime.page.route === "listing") {
      if (window.location.search || Object.keys(parsed).length) {
        runtime.listingRequest = parsed;
      } else {
        const identifier = String(runtime.page.listing_id || runtime.page.slug || "");
        if (!runtime.recommendationContext || [runtime.recommendationContext.listing_id, runtime.recommendationContext.slug].indexOf(identifier) === -1) runtime.listingRequest = {};
      }
      return;
    }
    runtime.listingRequest = {};
  }

  function navigate(page, path, entryRoute) {
    if (entryRoute === "browse") {
      runtime.request = null;
      runtime.matcher = initialMatcherState();
      runtime.results = null;
      runtime.recommendationContext = null;
      runtime.listingRequest = {};
      persistState();
    }
    runtime.page = page;
    window.history.pushState(page, "", path);
    if (entryRoute) track("entry_route_choice", { entry_route: entryRoute });
    loadRoute(true);
  }

  function stateMessage(title, body, kind, retryHandler) {
    const box = element("section", "state-message" + (kind ? " " + kind : ""));
    append(box, element("h2", "", title), element("p", "", body));
    if (retryHandler) append(box, button(copy("retry"), "button button-dark", retryHandler));
    return box;
  }

  function loadingView() {
    const target = clearMain();
    const section = element("section", "boot-state");
    const title = element("h1", "", copy("loading"));
    const lines = element("div", "loading-lines");
    lines.setAttribute("aria-hidden", "true");
    append(lines, element("span"), element("span"), element("span"));
    append(section, title, lines);
    target.appendChild(section);
    announce(copy("loading"));
  }

  function renderFailure(error) {
    const target = clearMain();
    const wrap = element("div", "page-width catalog-page");
    wrap.appendChild(stateMessage(copy("serviceUnavailable"), error && error.message ? error.message : copy("serviceUnavailableHelp"), "danger", function () { loadRoute(false); }));
    target.appendChild(wrap);
    announce(error && error.message ? error.message : copy("serviceUnavailable"), true);
    focusMain();
  }

  async function loadConfig() {
    const saved = sessionPayload();
    runtime.config = await getJSON(ENDPOINTS.config, { lang: runtime.lang });
    const issued = runtime.config.session_id;
    runtime.config.fresh_session_id = issued;
    runtime.config.session_id = chooseSessionToken(saved.session_id, issued);
    if (!runtime.matcher) runtime.matcher = initialMatcherState(saved.matcher);
    if (!runtime.request && saved.request && runtime.page.route !== "browse") runtime.request = saved.request;
    if (!runtime.recommendationContext) runtime.recommendationContext = safeRecommendationContext(saved.recommendation_context || {}, saved.recommendation_context && saved.recommendation_context.lang);
    persistState();
    return runtime.config;
  }

  function roundedCatalogAction(count) {
    if (!Number.isInteger(count) || count <= 0) return copy("browseCta");
    if (count > 50) return copy("browseRounded", { count: Math.floor(count / 10) * 10 });
    if (runtime.lang === "en" && count >= 50) return copy("browseRounded", { count: 50 });
    return copy("browseCount", { count: formatNumber(count) });
  }

  function createHero(results) {
    const hero = element("section", "hero");
    const copyBox = element("div", "hero-copy");
    const title = element("h1", "", copy("heroTitle"));
    const actions = element("div", "hero-actions");
    const guided = button(copy("guidedCta"), "button button-primary", function () {
      runtime.matcher = initialMatcherState();
      runtime.impressedListingIds = new Set();
      runtime.recommendationContext = null;
      persistState();
      track("matcher_start", { entry_route: "guided" });
      navigate({ route: "match", slug: null, listing_id: null }, "/monthly/match", "guided");
    });
    guided.appendChild(svgIcon("arrow"));
    const browse = actionLink(roundedCatalogAction(runtime.config.eligible_count), "/monthly/search", "button button-secondary", function (event) {
      event.preventDefault();
      navigate({ route: "browse", slug: null, listing_id: null }, "/monthly/search", "browse");
    });
    append(actions, guided, browse);
    append(copyBox, element("p", "eyebrow", copy("eyebrow")), title, element("p", "hero-intro", copy("heroIntro")), actions);
    hero.appendChild(copyBox);

    const first = (results || []).find(function (item) { return safeImageUrl(item && item.cover && item.cover.url); });
    if (first) {
      const figure = element("figure", "hero-photo");
      const image = element("img");
      image.src = safeImageUrl(first.cover.url);
      image.alt = first.cover.alt || first.title || "";
      image.width = 1200;
      image.height = 900;
      image.decoding = "async";
      append(figure, image, element("figcaption", "", first.title));
      hero.appendChild(figure);
    }
    return hero;
  }

  function proofItem(title, body) {
    const item = element("div", "proof-item");
    append(item, element("strong", "", title), element("span", "", body));
    return item;
  }

  function responseProof() {
    const message = contactState(runtime.config, runtime.lang).response_message;
    return message ? proofItem(message, "") : null;
  }

  function createProofStrip() {
    const strip = element("section", "proof-strip");
    strip.setAttribute("aria-label", runtime.lang === "ar" ? "معلومات موثوقة" : "Verified service information");
    append(
      strip,
      proofItem(copy("proofManaged"), copy("proofManagedText")),
      proofItem(copy("proofPrice"), copy("proofPriceText")),
      proofItem(copy("proofPrivacy"), copy("proofPrivacyText")),
      responseProof()
    );
    return strip;
  }

  function availabilityLabel(status) {
    if (status === "available") return copy("available");
    if (status === "unavailable") return copy("unavailable");
    return copy("pending");
  }

  function factsList(item) {
    const list = element("ul", "facts");
    const facts = item.facts || {};
    const values = [];
    if (facts.bedrooms === 0) values.push(copy("studioFact"));
    else if (facts.bedrooms !== null && facts.bedrooms !== undefined) values.push(copy("bedroomsFact", { count: formatNumber(facts.bedrooms) }));
    if (facts.bathrooms !== null && facts.bathrooms !== undefined) values.push(copy("bathroomsFact", { count: formatNumber(facts.bathrooms) }));
    if (facts.capacity !== null && facts.capacity !== undefined) values.push(copy("capacityFact", { count: formatNumber(facts.capacity) }));
    if (facts.floor_area_sqm !== null && facts.floor_area_sqm !== undefined) values.push(copy("areaFact", { count: formatNumber(facts.floor_area_sqm) }));
    values.forEach(function (value) { list.appendChild(element("li", "", value)); });
    return list;
  }

  function listingPath(item) {
    const safeSlug = typeof item.slug === "string" && /^[A-Za-z0-9_-]+$/.test(item.slug) ? item.slug : null;
    return safeSlug ? "/monthly/" + safeSlug : "/monthly/id/" + encodeURIComponent(item.id);
  }

  function openListing(event, item) {
    event.preventDefault();
    const page = { route: "listing", listing_id: String(item.id), slug: null };
    const guided = runtime.page.route !== "browse";
    runtime.recommendationContext = guided ? safeRecommendationContext(item, runtime.lang) : null;
    const sourceRequest = guided ? runtime.request : runtime.browseQuery;
    runtime.listingRequest = canonicalListingRequest(sourceRequest, item);
    persistState();
    navigate(page, listingPath(item) + queryString(runtime.listingRequest));
  }

  function createCard(item, index) {
    const card = element("article", "listing-card");
    const path = listingPath(item);
    const media = actionLink("", path, "listing-card-media", function (event) { openListing(event, item); });
    const imageUrl = safeImageUrl(item.cover && item.cover.url);
    if (imageUrl) {
      const image = element("img");
      image.src = imageUrl;
      image.alt = (item.cover && item.cover.alt) || item.title || "";
      image.width = 640;
      image.height = 480;
      image.loading = index > 2 ? "lazy" : "eager";
      image.decoding = "async";
      media.appendChild(image);
    }
    const body = element("div", "listing-card-body");
    const heading = element("h3");
    heading.appendChild(actionLink(item.title, path, "", function (event) { openListing(event, item); }));
    append(body, heading);
    if (item.neighborhood) body.appendChild(element("p", "listing-location", item.neighborhood));
    body.appendChild(factsList(item));
    if (item.summary) body.appendChild(element("p", "listing-summary", item.summary));
    const adjusted = adjustedDateWindow(item);
    if (adjusted) {
      body.appendChild(element("p", "availability adjusted-dates", copy("adjustedDates", {
        moveIn: adjusted.move_in,
        moveOut: adjusted.move_out
      })));
    }
    if (item.rating !== undefined && item.reviews_count) {
      body.appendChild(element("p", "rating-line", copy("rating", { rating: formatNumber(item.rating), count: formatNumber(item.reviews_count) })));
    }
    if (item.quote && item.quote.monthly_rate_sar !== undefined) {
      body.appendChild(element("p", "price-line", copy("perMonth", { amount: formatNumber(item.quote.monthly_rate_sar) })));
      const included = approvedIncluded(item.quote.included || []).map(function (key) { return copy(key); });
      if (included.length) body.appendChild(element("p", "card-included", copy("quoteIncludes", { items: included.join(runtime.lang === "ar" ? "، " : ", ") })));
    }
    const status = publicAvailabilityStatus(item.availability_status, Boolean(item.quote));
    if (status) {
      const availability = element("p", "availability " + status);
      append(availability, svgIcon(status === "available" ? "check" : "alert"), document.createTextNode(availabilityLabel(status)));
      body.appendChild(availability);
    }
    append(card, media, body);
    return card;
  }

  function catalogGrid(items) {
    const grid = element("div", "listing-grid");
    (items || []).forEach(function (item, index) { grid.appendChild(createCard(item, index + 1)); });
    return grid;
  }

  async function renderHome() {
    loadingView();
    const catalog = await getJSON(ENDPOINTS.browse, { lang: runtime.lang });
    const target = clearMain();
    target.appendChild(createHero(catalog.results));
    target.appendChild(createProofStrip());
    if (runtime.config.blockers && runtime.config.blockers.length) {
      const wrap = element("div", "page-width");
      wrap.appendChild(stateMessage(copy("partialService"), "", "warning"));
      target.appendChild(wrap);
    }
    if (catalog.results && catalog.results.length) {
      const preview = element("section", "page-width home-catalog-preview");
      const heading = element("div", "section-heading");
      const headingCopy = element("div");
      append(headingCopy, element("h2", "", copy("catalogPreview")), element("p", "", copy("catalogPreviewText")));
      heading.appendChild(headingCopy);
      heading.appendChild(actionLink(copy("viewCatalog"), "/monthly/search", "button button-outline", function (event) {
        event.preventDefault();
        navigate({ route: "browse", slug: null, listing_id: null }, "/monthly/search", "browse");
      }));
      append(preview, heading, catalogGrid(catalog.results.slice(0, 3)));
      target.appendChild(preview);
    }
    track("landing_view", {});
    announce(copy("heroTitle"));
    focusMain();
  }

  function matcherProgress(state) {
    const top = element("div", "matcher-top");
    const back = button(copy("back"), "back-button", function () {
      if (runtime.matcher.current === 0) {
        navigate({ route: "home", slug: null, listing_id: null }, "/monthly");
        return;
      }
      runtime.matcher = goBack(runtime.matcher);
      persistState();
      renderMatcher();
    });
    back.setAttribute("aria-label", copy("back"));
    back.replaceChildren(svgIcon("back"));
    const shell = element("div", "progress-shell");
    const text = element("div", "progress-copy");
    const current = Math.min(state.current + 1, state.steps.length);
    append(text, element("span", "", copy("progress", { current: current, total: state.steps.length })), element("span", "", Math.round(current / state.steps.length * 100) + "%"));
    const trackNode = element("div", "progress-track");
    trackNode.setAttribute("role", "progressbar");
    trackNode.setAttribute("aria-valuemin", "1");
    trackNode.setAttribute("aria-valuemax", String(state.steps.length));
    trackNode.setAttribute("aria-valuenow", String(current));
    const value = element("div", "progress-value");
    value.style.transform = "scaleX(" + (current / state.steps.length) + ")";
    trackNode.appendChild(value);
    append(shell, text, trackNode);
    append(top, back, shell);
    return top;
  }

  function questionShell(title, hint) {
    const panel = element("section", "question-panel");
    panel.setAttribute("data-view", "question");
    append(panel, element("h1", "", title), element("p", "question-hint", hint));
    return panel;
  }

  function recordAnswer(question, answer) {
    const context = { question: question, answer: answer };
    return track("matcher_answer", context);
  }

  function applyMatcherAnswer(step, value) {
    runtime.matcher = answerStep(runtime.matcher, step, value);
    runtime.impressedListingIds = new Set();
    runtime.recommendationContext = null;
    persistState();
    if (step === "dates") {
      recordAnswer("move_in", value.move_in);
      if (value.date_mode === "departure") recordAnswer("move_out", value.move_out);
      else recordAnswer("duration_months", Number(value.duration_months));
    } else if (step === "place") {
      recordAnswer("place", value.id);
    } else {
      recordAnswer(step, value);
    }
    if (runtime.matcher.current >= runtime.matcher.steps.length) submitMatch();
    else renderMatcher();
  }

  function choiceList(values, selected, handler) {
    const list = element("div", "choices");
    values.forEach(function (row) {
      const node = button(row.label, "choice", function () { handler(row.value); });
      node.setAttribute("aria-pressed", String(JSON.stringify(selected) === JSON.stringify(row.value)));
      append(node, svgIcon("arrow"));
      list.appendChild(node);
    });
    return list;
  }

  function renderPurpose(panel) {
    const values = PURPOSE_KEYS.map(function (key) { return { value: key, label: copy(key) }; });
    panel.appendChild(choiceList(values, runtime.matcher.answers.purpose, function (value) { applyMatcherAnswer("purpose", value); }));
  }

  function placesForPurpose() {
    const configured = [].concat((runtime.config && runtime.config.places) || [], (runtime.config && runtime.config.neighborhoods) || []);
    const seen = {};
    return configured.filter(function (place) {
      if (!place || !place.id || seen[place.id]) return false;
      seen[place.id] = true;
      return true;
    });
  }

  function placeTitle(purpose) {
    if (purpose === "treatment") return copy("placeTitleTreatment");
    if (purpose === "visit") return copy("placeTitleVisit");
    return copy("placeTitleWork");
  }

  function renderPlace(panel) {
    const values = placesForPurpose().map(function (place) {
      return {
        value: {
          kind: place.kind,
          id: place.id,
          label: runtime.lang === "ar" ? place.label_ar : place.label_en
        },
        label: runtime.lang === "ar" ? place.label_ar : place.label_en
      };
    });
    if (!values.length) {
      panel.appendChild(stateMessage(copy("placeUnavailable"), copy("placeHint"), "warning"));
      return;
    }
    panel.appendChild(choiceList(values, runtime.matcher.answers.place, function (value) { applyMatcherAnswer("place", value); }));
  }

  function renderResidents(panel) {
    const values = [1, 2, 3, 4, 5, 6].map(function (count) { return { value: count, label: formatNumber(count) }; });
    panel.appendChild(choiceList(values, runtime.matcher.answers.residents, function (value) { applyMatcherAnswer("residents", value); }));
    const form = element("form", "date-form");
    const field = element("div", "form-field");
    const label = element("label", "", copy("residentsCustom"));
    label.htmlFor = "custom-residents";
    const input = element("input");
    input.id = "custom-residents";
    input.type = "number";
    input.min = "7";
    input.max = "50";
    input.inputMode = "numeric";
    append(field, label, input);
    const submit = button(copy("continue"), "button button-dark");
    submit.type = "submit";
    append(form, field, submit);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const value = Number(input.value);
      if (Number.isInteger(value) && value >= 7 && value <= 50) applyMatcherAnswer("residents", value);
      else announce(copy("residentsLabel"), true);
    });
    panel.appendChild(form);
  }

  function renderSleeping(panel) {
    const values = SLEEPING.map(function (row) { return { value: row[0], label: copy(row[1]) }; });
    panel.appendChild(choiceList(values, runtime.matcher.answers.sleeping, function (value) { applyMatcherAnswer("sleeping", value); }));
  }

  function formField(id, labelText, type, value) {
    const field = element("div", "form-field");
    const label = element("label", "", labelText);
    label.htmlFor = id;
    const input = element("input");
    input.id = id;
    input.type = type;
    if (value) input.value = value;
    append(field, label, input);
    return { field: field, input: input };
  }

  function renderDates(panel) {
    const answers = runtime.matcher.answers;
    const form = element("form", "date-form");
    const moveIn = formField("matcher-move-in", copy("moveIn"), "date", answers.move_in);
    const mode = answers.date_mode === "departure" ? "departure" : "duration";
    const modes = element("fieldset", "segmented");
    const legend = element("legend", "fieldset-title", copy("duration"));
    modes.appendChild(legend);
    const durationMode = button(copy("durationChoice"), "choice");
    const departureMode = button(copy("departureChoice"), "choice");
    durationMode.setAttribute("aria-pressed", String(mode === "duration"));
    departureMode.setAttribute("aria-pressed", String(mode === "departure"));
    append(modes, durationMode, departureMode);
    const variable = element("div");
    function drawVariable(selected) {
      variable.replaceChildren();
      durationMode.setAttribute("aria-pressed", String(selected === "duration"));
      departureMode.setAttribute("aria-pressed", String(selected === "departure"));
      if (selected === "departure") {
        const moveOut = formField("matcher-move-out", copy("moveOut"), "date", answers.move_out);
        variable.appendChild(moveOut.field);
      } else {
        const field = element("div", "form-field");
        const label = element("label", "", copy("duration"));
        label.htmlFor = "matcher-duration";
        const select = element("select");
        select.id = "matcher-duration";
        for (let count = 1; count <= 6; count += 1) {
          const option = element("option", "", count === 1 ? copy("monthOne") : copy("monthsCount", { count: formatNumber(count) }));
          option.value = String(count);
          if (Number(answers.duration_months || 1) === count) option.selected = true;
          select.appendChild(option);
        }
        append(field, label, select);
        variable.appendChild(field);
      }
      variable.dataset.mode = selected;
    }
    durationMode.addEventListener("click", function () { drawVariable("duration"); });
    departureMode.addEventListener("click", function () { drawVariable("departure"); });
    drawVariable(mode);
    const error = element("p", "field-error");
    error.id = "dates-error";
    error.setAttribute("aria-live", "assertive");
    const submit = button(copy("continue"), "button button-dark");
    submit.type = "submit";
    append(form, moveIn.field, modes, variable, error, submit);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const value = { date_mode: variable.dataset.mode, move_in: moveIn.input.value };
      if (value.date_mode === "departure") {
        const input = variable.querySelector("input");
        value.move_out = input && input.value;
      } else {
        const select = variable.querySelector("select");
        value.duration_months = Number(select && select.value);
      }
      const valid = /^\d{4}-\d{2}-\d{2}$/.test(value.move_in || "") && (
        value.date_mode === "duration" ? Number.isInteger(value.duration_months) && value.duration_months >= 1 && value.duration_months <= 6 : /^\d{4}-\d{2}-\d{2}$/.test(value.move_out || "") && value.move_out > value.move_in
      );
      if (!valid) {
        error.textContent = copy("datesRequired");
        announce(copy("datesRequired"), true);
        return;
      }
      applyMatcherAnswer("dates", value);
    });
    panel.appendChild(form);
  }

  function renderFlexibility(panel) {
    const values = [
      { value: "fixed", label: copy("fixedDates") },
      { value: "plus_minus_7", label: copy("flexibleDates") }
    ];
    panel.appendChild(choiceList(values, runtime.matcher.answers.flexibility, function (value) { applyMatcherAnswer("flexibility", value); }));
  }

  function renderMatcher() {
    const target = clearMain();
    const wrap = element("div", "narrow-width matcher-page");
    runtime.matcher = runtime.matcher || initialMatcherState();
    wrap.appendChild(matcherProgress(runtime.matcher));
    const step = runtime.matcher.steps[Math.min(runtime.matcher.current, runtime.matcher.steps.length - 1)];
    let panel;
    if (step === "purpose") {
      panel = questionShell(copy("purposeTitle"), copy("purposeHint"));
      renderPurpose(panel);
    } else if (step === "place") {
      panel = questionShell(placeTitle(runtime.matcher.answers.purpose), copy("placeHint"));
      renderPlace(panel);
    } else if (step === "residents") {
      panel = questionShell(copy("residentsTitle"), copy("residentsHint"));
      renderResidents(panel);
    } else if (step === "sleeping") {
      panel = questionShell(copy("sleepingTitle"), copy("sleepingHint"));
      renderSleeping(panel);
    } else if (step === "dates") {
      panel = questionShell(copy("datesTitle"), copy("datesHint"));
      renderDates(panel);
    } else {
      panel = questionShell(copy("flexibilityTitle"), copy("flexibilityHint"));
      renderFlexibility(panel);
    }
    wrap.appendChild(panel);
    target.appendChild(wrap);
    announce(panel.querySelector("h1").textContent);
    window.requestAnimationFrame(focusQuestion);
  }

  async function submitMatch() {
    loadingView();
    announce(copy("matching"));
    try {
      runtime.request = buildMatchRequest(runtime.matcher.answers);
      persistState();
      track("matcher_completion", eventContextFromRequest(runtime.request));
      runtime.results = await postJSON(ENDPOINTS.match, Object.assign({ lang: runtime.lang }, runtime.request));
      renderResults(runtime.results);
    } catch (error) {
      runtime.matcher = goBack(runtime.matcher);
      persistState();
      renderFailure(error);
    }
  }

  function eventContextFromRequest(request) {
    const context = {
      purpose: request.purpose,
      move_in: request.move_in,
      entry_route: "guided"
    };
    if (request.duration_months) context.duration_months = request.duration_months;
    if (request.move_out) context.move_out = request.move_out;
    if (request.place) context.place_id = request.place.id;
    return context;
  }

  function recommendationCard(item, index) {
    const card = element("article", "recommendation");
    const compact = createCard(item, index);
    const media = compact.querySelector(".listing-card-media");
    const originalBody = compact.querySelector(".listing-card-body");
    const content = element("div", "recommendation-copy");
    while (originalBody && originalBody.firstChild) content.appendChild(originalBody.firstChild);
    if (item.reasons && item.reasons.length) {
      content.appendChild(element("h4", "", copy("whyFits")));
      const reasons = element("ul", "reason-list");
      item.reasons.slice(0, 4).forEach(function (reason) {
        const row = element("li");
        append(row, svgIcon("check"), document.createTextNode(reason));
        reasons.appendChild(row);
      });
      content.appendChild(reasons);
    }
    if (item.tradeoff) {
      const trade = element("div", "tradeoff");
      append(trade, element("strong", "", copy("tradeoff")), element("p", "", item.tradeoff));
      content.appendChild(trade);
    }
    const link = actionLink(copy("viewHome"), listingPath(item), "button button-dark", function (event) { openListing(event, item); });
    content.appendChild(link);
    append(card, media, content);
    return card;
  }

  function resultsSection(title, intro, items, recommended) {
    const section = element("section", "results-section");
    const heading = element("div", "section-heading");
    const words = element("div");
    append(words, element("h2", "", title), intro ? element("p", "", intro) : null);
    heading.appendChild(words);
    section.appendChild(heading);
    if (recommended) {
      const grid = element("div", "recommended-grid");
      items.forEach(function (item, index) { grid.appendChild(recommendationCard(item, index + 1)); });
      section.appendChild(grid);
    } else {
      section.appendChild(catalogGrid(items));
    }
    return section;
  }

  function resultCounts(result) {
    const list = element("ul", "result-counts");
    if (result.pending_count) list.appendChild(element("li", "", copy("pendingAvailability", { count: formatNumber(result.pending_count) })));
    if (result.unavailable_count) list.appendChild(element("li", "", copy("unavailableCount", { count: formatNumber(result.unavailable_count) })));
    return list;
  }

  function renderResults(result) {
    const target = clearMain();
    const wrap = element("div", "page-width results-page");
    const heading = element("div", "section-heading");
    const words = element("div");
    append(words, element("p", "eyebrow", result.catalog_claim || copy("eyebrow")), element("h1", "", copy("resultsTitle")));
    heading.appendChild(words);
    heading.appendChild(button(copy("startOver"), "button button-outline", function () {
      runtime.matcher = initialMatcherState();
      runtime.request = null;
      runtime.results = null;
      runtime.recommendationContext = null;
      runtime.impressedListingIds = new Set();
      persistState();
      renderMatcher();
    }));
    append(wrap, heading, resultCounts(result));
    if (result.empty_state) {
      wrap.appendChild(stateMessage(result.empty_state.message || copy("noExact"), result.near_matches && result.near_matches.length ? copy("nearHelp") : "", "warning"));
    }
    if (result.top && result.top.length) wrap.appendChild(resultsSection(copy("bestThree"), copy("bestThreeText"), result.top, true));
    if (result.near_matches && result.near_matches.length) wrap.appendChild(resultsSection(copy("nearMatches"), copy("nearHelp"), result.near_matches, true));
    if (result.alternatives && result.alternatives.length) wrap.appendChild(resultsSection(copy("strongOptions"), "", result.alternatives, false));
    if (result.catalog && result.catalog.length) wrap.appendChild(resultsSection(copy("allAvailable"), "", result.catalog, false));
    if (!(result.top && result.top.length) && !(result.near_matches && result.near_matches.length)) {
      if (!result.pending_count && requestIsComplete(runtime.request)) {
        const help = stateMessage(copy("generalHelpTitle"), copy("generalHelpText"), "warning");
        const control = button(copy("generalHelpAction"), "button button-primary", function () { prepareGeneralHelp(control); });
        const currentContact = contactState(runtime.config, runtime.lang);
        control.disabled = currentContact.disabled;
        if (currentContact.message) help.appendChild(element("p", "contact-blocked", currentContact.message));
        help.appendChild(control);
        if (currentContact.response_message) {
          const response = element("p", "contact-note", currentContact.response_message);
          response.setAttribute("data-response-window", "");
          help.appendChild(response);
        }
        wrap.appendChild(help);
      }
      wrap.appendChild(actionLink(copy("browseCta"), "/monthly/search", "button button-outline", function (event) {
        event.preventDefault();
        navigate({ route: "browse", slug: null, listing_id: null }, "/monthly/search", "browse");
      }));
    }
    target.appendChild(wrap);
    const ids = rankedImpressionIds(result).slice(0, 100);
    track("results_view", Object.assign(eventContextFromRequest(runtime.request || {}), { listing_ids: ids }));
    ids.forEach(function (id, index) {
      if (runtime.impressedListingIds.has(id)) return;
      runtime.impressedListingIds.add(id);
      track("result_impression", { listing_id: id, rank: index + 1 });
    });
    announce(copy("resultsTitle"));
    focusMain();
  }

  function selectField(id, labelText, options, selected) {
    const field = element("div", "form-field");
    const label = element("label", "", labelText);
    label.htmlFor = id;
    const select = element("select");
    select.id = id;
    options.forEach(function (row) {
      const option = element("option", "", row.label);
      option.value = String(row.value);
      if (optionIsSelected(selected, row.value)) option.selected = true;
      select.appendChild(option);
    });
    append(field, label, select);
    return { field: field, select: select };
  }

  function browseFilterForm() {
    const shell = element("section", "filters");
    shell.appendChild(element("h2", "", copy("filtersTitle")));
    const form = element("form", "filter-form");
    const query = runtime.browseQuery;
    const moveIn = formField("browse-move-in", copy("moveIn"), "date", query.move_in);
    const duration = selectField("browse-duration", copy("duration"), [
      { value: "", label: copy("duration") },
      { value: 1, label: copy("monthOne") },
      { value: 2, label: copy("monthsCount", { count: 2 }) },
      { value: 3, label: copy("monthsCount", { count: 3 }) },
      { value: 4, label: copy("monthsCount", { count: 4 }) },
      { value: 5, label: copy("monthsCount", { count: 5 }) },
      { value: 6, label: copy("monthsCount", { count: 6 }) }
    ], query.duration_months);
    const residents = formField("browse-residents", copy("residentsOptional"), "number", query.residents);
    residents.input.min = "1";
    residents.input.max = "50";
    const bedrooms = selectField("browse-bedrooms", copy("bedrooms"), [
      { value: "", label: copy("allBedrooms") },
      { value: 0, label: copy("studio") },
      { value: 1, label: copy("oneBedroom") },
      { value: 2, label: copy("twoBedrooms") },
      { value: 3, label: copy("threeBedrooms") },
      { value: 4, label: copy("fourBedrooms") }
    ], query.bedrooms);
    const neighborhoods = [{ value: "", label: copy("allNeighborhoods") }].concat(((runtime.config && runtime.config.neighborhoods) || []).map(function (place) {
      return { value: place.id, label: runtime.lang === "ar" ? place.label_ar : place.label_en };
    }));
    const neighborhood = selectField("browse-neighborhood", copy("neighborhood"), neighborhoods, query.neighborhood);
    const places = [{ value: "", label: copy("allPlaces") }].concat(((runtime.config && runtime.config.places) || []).map(function (place) {
      return { value: place.id, label: runtime.lang === "ar" ? place.label_ar : place.label_en };
    }));
    const important = selectField("browse-place", copy("importantPlace"), places, query.place && query.place.id);
    const actions = element("div", "filter-actions");
    const submit = button(copy("applyFilters"), "button button-dark");
    submit.type = "submit";
    const clear = button(copy("clearFilters"), "button button-outline", function () {
      runtime.browseQuery = {};
      window.history.replaceState(runtime.page, "", "/monthly/search");
      renderBrowse();
    });
    append(actions, submit, clear);
    append(form, moveIn.field, duration.field, residents.field, bedrooms.field, neighborhood.field, important.field, actions);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const values = {
        move_in: moveIn.input.value,
        duration_months: duration.select.value,
        residents: residents.input.value,
        bedrooms: bedrooms.select.value,
        neighborhood: neighborhood.select.value
      };
      if (important.select.value) {
        const place = ((runtime.config && runtime.config.places) || []).find(function (row) { return row.id === important.select.value; });
        if (place) values.place = { kind: place.kind, id: place.id, label: runtime.lang === "ar" ? place.label_ar : place.label_en };
      }
      Object.keys(values).forEach(function (key) { if (values[key] === "") delete values[key]; });
      if (values.move_in && !values.duration_months) {
        announce(copy("datesRequired"), true);
        return;
      }
      runtime.browseQuery = values;
      window.history.replaceState(runtime.page, "", "/monthly/search" + queryString(values));
      renderBrowse();
    });
    shell.appendChild(form);
    return shell;
  }

  async function renderBrowse() {
    loadingView();
    try {
      const values = Object.assign({ lang: runtime.lang }, runtime.browseQuery);
      const result = await getJSON(ENDPOINTS.browse, values);
      const target = clearMain();
      const wrap = element("div", "page-width catalog-page");
      const heading = element("div", "section-heading");
      const words = element("div");
      append(words, element("h1", "", copy("browseTitle")), element("p", "", copy("browseIntro")));
      append(heading, words, element("strong", "", copy("homesCount", { count: formatNumber(result.counts.results) })));
      append(wrap, heading, browseFilterForm());
      const counts = resultCounts({ pending_count: result.counts.pending, unavailable_count: result.counts.unavailable });
      if (result.counts.missing_price) counts.appendChild(element("li", "", copy("missingPriceCount", { count: formatNumber(result.counts.missing_price) })));
      wrap.appendChild(counts);
      if (result.results && result.results.length) wrap.appendChild(catalogGrid(result.results));
      else wrap.appendChild(stateMessage(copy("noBrowseResults"), result.counts.pending ? copy("pendingBrowse") : "", "warning"));
      target.appendChild(wrap);
      announce(copy("homesCount", { count: result.counts.results }));
      focusMain();
    } catch (error) {
      renderFailure(error);
    }
  }

  function listingQuoteRequest(request) {
    const values = {};
    if (request) {
      ["move_in", "move_out", "duration_months", "residents", "purpose"].forEach(function (key) {
        if (request[key] !== undefined) values[key] = request[key];
      });
      if (request.place) values.place = request.place;
    }
    return values;
  }

  function listingQuery(identifier, bySlug) {
    const values = Object.assign({ lang: runtime.lang }, listingQuoteRequest(runtime.listingRequest));
    if (bySlug) values.lookup = "slug";
    return "/api/monthly/listing/" + encodeURIComponent(identifier) + queryString(values);
  }

  function licenceDetails(listing) {
    const section = element("section", "licence-section");
    section.appendChild(element("h2", "", copy("licence")));
    const licence = listing.licence || {};
    const list = element("ul", "facts");
    if (licence.number) list.appendChild(element("li", "", copy("licenceNumber", { value: licence.number })));
    if (licence.expires) list.appendChild(element("li", "", copy("licenceExpiry", { value: licence.expires })));
    section.appendChild(list);
    return section;
  }

  function gallery(listing) {
    const section = element("section", "gallery");
    section.setAttribute("aria-label", runtime.lang === "ar" ? "صور البيت" : "Home photos");
    (listing.images || []).forEach(function (photo, index) {
      const url = safeImageUrl(photo.url);
      if (!url) return;
      const figure = element("figure");
      const image = element("img");
      image.src = url;
      image.alt = photo.alt || listing.title || "";
      image.width = index === 0 ? 1200 : 600;
      image.sizes = index === 0 ? "(min-width: 768px) 50vw, 100vw" : "(min-width: 768px) 25vw, 50vw";
      image.loading = index === 0 ? "eager" : "lazy";
      image.decoding = "async";
      figure.appendChild(image);
      section.appendChild(figure);
    });
    return section;
  }

  function listingContent(listing) {
    const content = element("div", "listing-content");
    const title = element("section", "listing-title");
    append(title, element("h1", "", listing.title));
    if (listing.neighborhood) title.appendChild(element("p", "listing-location", listing.neighborhood));
    title.appendChild(factsList(listing));
    if (listing.rating !== undefined && listing.reviews_count) title.appendChild(element("p", "rating-line", copy("rating", { rating: formatNumber(listing.rating), count: formatNumber(listing.reviews_count) })));
    if (listing.tagline) title.appendChild(element("p", "listing-tagline", listing.tagline));
    if (listing.highlights && listing.highlights.length) {
      const highlights = element("ul", "listing-highlights");
      listing.highlights.forEach(function (item) {
        if (!item || !item.label) return;
        const row = element("li");
        append(row, svgIcon("check"), document.createTextNode(item.label));
        highlights.appendChild(row);
      });
      title.appendChild(highlights);
    }
    content.appendChild(title);
    const context = runtime.recommendationContext;
    if (context && context.listing_id === String(listing.id) && context.lang === runtime.lang) {
      const proof = element("section", "recommendation-proof");
      proof.appendChild(element("h2", "", copy("whyRecommended")));
      if (context.reasons.length) {
        const reasons = element("ul", "reason-list");
        context.reasons.forEach(function (reason) {
          const row = element("li");
          append(row, svgIcon("check"), document.createTextNode(reason));
          reasons.appendChild(row);
        });
        proof.appendChild(reasons);
      }
      if (context.tradeoff) {
        const trade = element("div", "tradeoff");
        append(trade, element("strong", "", copy("tradeoff")), element("p", "", context.tradeoff));
        proof.appendChild(trade);
      }
      content.appendChild(proof);
    }
    if (listing.story && listing.story.length) {
      const story = element("section", "story-section");
      story.appendChild(element("h2", "", copy("story")));
      const list = element("div", "story-list");
      listing.story.forEach(function (item, index) {
        const row = element("article", "story-item");
        const photo = (listing.images || [])[index + 1] || (listing.images || [])[0];
        const photoUrl = safeImageUrl(photo && photo.url);
        if (photoUrl) {
          const image = element("img", "story-photo");
          image.src = photoUrl;
          image.alt = (photo && photo.alt) || listing.title || "";
          image.width = 720;
          image.sizes = "(min-width: 768px) 32vw, 100vw";
          image.loading = "lazy";
          image.decoding = "async";
          row.appendChild(image);
        }
        const words = element("div", "story-copy");
        append(words, element("h3", "", item.title), element("p", "", item.body));
        row.appendChild(words);
        list.appendChild(row);
      });
      append(story, list);
      content.appendChild(story);
    }
    if (listing.amenity_groups && listing.amenity_groups.length) {
      const amenities = element("section", "amenities-section");
      amenities.appendChild(element("h2", "", copy("amenities")));
      const groups = element("div", "amenity-groups");
      listing.amenity_groups.forEach(function (group) {
        const block = element("section");
        block.appendChild(element("h3", "", group.label));
        const list = element("ul", "amenity-list");
        (group.items || []).forEach(function (item) {
          const row = element("li");
          append(row, svgIcon("check"), document.createTextNode(item.label));
          list.appendChild(row);
        });
        append(block, list);
        groups.appendChild(block);
      });
      append(amenities, groups);
      content.appendChild(amenities);
    }
    if (listing.location && (listing.location.neighborhood || listing.location.description)) {
      const location = element("section", "location-section");
      append(location, element("h2", "", copy("location")));
      if (listing.location.neighborhood) location.appendChild(element("h3", "", listing.location.neighborhood));
      if (listing.location.description) location.appendChild(element("p", "", listing.location.description));
      content.appendChild(location);
    }
    return content;
  }

  function quoteLabel(item, key) {
    if (!item || typeof item !== "object") return "";
    return item[runtime.lang === "ar" ? "label_ar" : "label_en"] || "";
  }

  function requestIsComplete(request) {
    return Boolean(request && request.purpose && request.residents && request.sleeping && request.move_in && (request.duration_months || request.move_out) && request.flexibility && (request.purpose === "family" || request.place));
  }

  function quoteCard(listing, quote, status) {
    const card = element("aside", "price-card");
    card.appendChild(element("h2", "", copy("priceTitle")));
    if (!quote) {
      let message = copy("chooseDatesForPrice");
      if (status === "pending") message = copy("quotePending");
      if (status === "unavailable") message = copy("quoteUnavailable");
      if (status === "price_missing") message = copy("quoteMissing");
      card.appendChild(element("p", "", message));
      card.appendChild(stayDetailsForm(listing));
      return card;
    }
    const total = element("div", "price-total");
    append(total,
      element("strong", "", copy("perMonth", { amount: formatNumber(quote.monthly_rate_sar) })),
      element("span", "", copy("stayTotal") + ": " + formatNumber(quote.stay_total_sar) + (runtime.lang === "ar" ? " ر.س" : " SAR"))
    );
    card.appendChild(total);
    const terms = element("ul", "terms-list");
    const included = approvedIncluded(quote.included || []).map(function (key) { return copy(key); }).join(runtime.lang === "ar" ? "، " : ", ");
    const cleaning = quoteLabel(quote.cleaning, "cleaning");
    const utilities = quoteLabel(quote.utilities, "utilities");
    const deposit = quote.deposit || {};
    const refund = deposit[runtime.lang === "ar" ? "refund_ar" : "refund_en"] || "";
    const depositText = deposit.amount_sar !== undefined ? formatNumber(deposit.amount_sar) + (runtime.lang === "ar" ? " ر.س. " : " SAR. ") + refund : refund;
    const payments = (quote.payment_methods || []).map(function (method) { return method[runtime.lang] || ""; }).filter(Boolean).join(runtime.lang === "ar" ? "، " : ", ");
    [
      [copy("included"), included],
      [copy("utilities"), utilities],
      [copy("cleaning"), cleaning],
      [copy("deposit"), depositText],
      [copy("paymentMethods"), payments]
    ].forEach(function (row) {
      if (!row[1]) return;
      const item = element("li");
      append(item, element("strong", "", row[0]), element("span", "", row[1]));
      terms.appendChild(item);
    });
    card.appendChild(terms);
    const preliminary = quote[runtime.lang === "ar" ? "preliminary_label_ar" : "preliminary_label_en"];
    if (preliminary) card.appendChild(element("p", "preliminary-note", preliminary));
    const currentContact = contactState(runtime.config, runtime.lang);
    if (requestIsComplete(runtime.listingRequest)) {
      const contact = button(copy("contactWhatsApp"), "button button-primary contact-action", function () { prepareWhatsApp(contact, listing); });
      contact.disabled = currentContact.disabled;
      if (currentContact.message) card.appendChild(element("p", "contact-blocked", currentContact.message));
      card.appendChild(contact);
    } else {
      card.appendChild(element("p", "contact-blocked", copy("completeDetails")));
      card.appendChild(stayDetailsForm(listing));
    }
    if (currentContact.response_message) card.appendChild(element("p", "contact-note", currentContact.response_message));
    return card;
  }

  function stayDetailsForm(listing) {
    const form = element("form", "date-form");
    const saved = runtime.listingRequest || {};
    const purpose = selectField("listing-purpose", copy("selectPurpose"), PURPOSE_KEYS.map(function (key) { return { value: key, label: copy(key) }; }), saved.purpose || "family");
    const residents = formField("listing-residents", copy("residentsLabel"), "number", saved.residents || 1);
    residents.input.min = "1";
    residents.input.max = "50";
    const sleeping = selectField("listing-sleeping", copy("selectSleeping"), SLEEPING.map(function (row) { return { value: row[0], label: copy(row[1]) }; }), saved.sleeping || "flexible");
    const moveIn = formField("listing-move-in", copy("moveIn"), "date", saved.move_in);
    const usesMoveOut = validDate(saved.move_out) && validDate(saved.move_in) && saved.move_out > saved.move_in;
    const moveOut = usesMoveOut ? formField("listing-move-out", copy("moveOut"), "date", saved.move_out) : null;
    const duration = usesMoveOut ? null : selectField("listing-duration", copy("duration"), [1, 2, 3, 4, 5, 6].map(function (count) { return { value: count, label: count === 1 ? copy("monthOne") : copy("monthsCount", { count: formatNumber(count) }) }; }), saved.duration_months || 1);
    const flexibility = selectField("listing-flexibility", copy("selectFlexibility"), [
      { value: "fixed", label: copy("fixedDates") },
      { value: "plus_minus_7", label: copy("flexibleDates") }
    ], saved.flexibility || "fixed");
    const placeOptions = placesForPurpose();
    const place = selectField("listing-place", copy("importantPlace"), [{ value: "", label: copy("allPlaces") }].concat(placeOptions.map(function (item) {
      return { value: item.id, label: runtime.lang === "ar" ? item.label_ar : item.label_en };
    })), saved.place && saved.place.id);
    const placeField = place.field;
    function togglePlace() {
      placeField.hidden = purpose.select.value === "family";
    }
    purpose.select.addEventListener("change", togglePlace);
    togglePlace();
    const error = element("p", "field-error");
    error.setAttribute("aria-live", "assertive");
    const submit = button(copy("getOfficialPrice"), "button button-primary");
    submit.type = "submit";
    append(form, purpose.field, residents.field, sleeping.field, moveIn.field, moveOut ? moveOut.field : duration.field, flexibility.field, placeField, error, submit);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const request = {
        purpose: purpose.select.value,
        residents: Number(residents.input.value),
        sleeping: sleeping.select.value,
        move_in: moveIn.input.value,
        flexibility: flexibility.select.value
      };
      if (moveOut) request.move_out = moveOut.input.value;
      else request.duration_months = Number(duration.select.value);
      if (request.purpose !== "family") {
        const selected = placeOptions.find(function (item) { return item.id === place.select.value; });
        if (selected) request.place = { kind: selected.kind, id: selected.id, label: runtime.lang === "ar" ? selected.label_ar : selected.label_en };
      }
      if (!requestIsComplete(request) || !/^\d{4}-\d{2}-\d{2}$/.test(request.move_in)) {
        error.textContent = copy("datesRequired");
        announce(error.textContent, true);
        return;
      }
      runtime.listingRequest = request;
      persistState();
      window.history.replaceState(runtime.page, "", listingPath(listing) + queryString(runtime.listingRequest));
      loadListing(listing.id, false);
    });
    return form;
  }

  async function prepareWhatsApp(control, listing) {
    control.disabled = true;
    control.textContent = copy("preparingWhatsApp");
    announce(copy("preparingWhatsApp"));
    try {
      const handoff = await withSessionRetry(function (activeSessionId) {
        return postJSON(ENDPOINTS.lead, {
          session_id: activeSessionId,
          listing_id: String(listing.id),
          request: runtime.listingRequest,
          lang: runtime.lang
        });
      });
      const handoffUrl = safeWhatsAppUrl(handoff.url);
      if (!handoffUrl) throw new Error(copy("leadFailed"));
      announce(copy("openingWhatsApp", { reference: handoff.lead_reference }));
      window.location.assign(handoffUrl);
    } catch (error) {
      control.disabled = false;
      control.textContent = copy("contactWhatsApp");
      announce(error.message || copy("leadFailed"), true);
    }
  }

  async function prepareGeneralHelp(control) {
    control.disabled = true;
    control.textContent = copy("preparingWhatsApp");
    announce(copy("preparingWhatsApp"));
    try {
      const handoff = await withSessionRetry(function (activeSessionId) {
        return postJSON(ENDPOINTS.lead, {
          session_id: activeSessionId,
          general_help: true,
          request: runtime.request,
          lang: runtime.lang
        });
      });
      const handoffUrl = safeWhatsAppUrl(handoff.url);
      if (!handoffUrl) throw new Error(copy("leadFailed"));
      const responseMessage = responseWindowMessage(handoff, runtime.lang);
      if (responseMessage && control.parentNode) {
        let note = control.parentNode.querySelector("[data-response-window]");
        if (!note) {
          note = element("p", "contact-note");
          note.setAttribute("data-response-window", "");
          control.parentNode.appendChild(note);
        }
        note.textContent = responseMessage;
      }
      announce(copy("openingWhatsApp", { reference: handoff.lead_reference }) + (responseMessage ? " " + responseMessage : ""));
      window.location.assign(handoffUrl);
    } catch (error) {
      control.disabled = false;
      control.textContent = copy("generalHelpAction");
      announce(error.message || copy("leadFailed"), true);
    }
  }

  function renderListingPage(listing, quote, status) {
    const target = clearMain();
    const wrap = element("article", "page-width listing-page");
    wrap.appendChild(gallery(listing));
    const layout = element("div", "listing-layout");
    layout.appendChild(listingContent(listing));
    const price = element("div", "price-column");
    price.appendChild(quoteCard(listing, quote, status));
    layout.appendChild(price);
    wrap.appendChild(layout);
    wrap.appendChild(licenceDetails(listing));
    target.appendChild(wrap);
    const currentContact = contactState(runtime.config, runtime.lang);
    if (quote && requestIsComplete(runtime.listingRequest) && !currentContact.disabled) {
      const mobile = element("div", "sticky-mobile-action");
      const contact = button(copy("contactWhatsApp"), "button button-primary", function () { prepareWhatsApp(contact, listing); });
      mobile.appendChild(contact);
      target.appendChild(mobile);
    }
    track("listing_view", { listing_id: String(listing.id) });
    announce(listing.title);
    focusMain();
  }

  async function loadListing(identifier, bySlug) {
    loadingView();
    try {
      const result = await requestJSON(listingQuery(identifier, bySlug));
      runtime.currentListing = result.listing;
      runtime.quote = result.quote;
      renderListingPage(result.listing, result.quote, result.quote_status);
    } catch (error) {
      if (error.code === "listing_not_found") {
        renderFailure(new Error(copy("listingNotFound")));
      } else {
        renderFailure(error);
      }
    }
  }

  async function localizeRecommendationContext() {
    const context = runtime.recommendationContext;
    if (!context || context.lang === runtime.lang || !requestIsComplete(runtime.request)) return;
    const result = await postJSON(ENDPOINTS.match, Object.assign({ lang: runtime.lang }, runtime.request));
    const item = [].concat(result.top || [], result.near_matches || [], result.alternatives || []).find(function (row) {
      return String(row.id) === context.listing_id;
    });
    runtime.recommendationContext = item ? safeRecommendationContext(item, runtime.lang) : null;
    persistState();
  }

  async function loadRoute(withFocus) {
    try {
      if (!runtime.config) await loadConfig();
      if (runtime.page.route === "home") await renderHome();
      else if (runtime.page.route === "match") {
        if (runtime.matcher.current >= runtime.matcher.steps.length && requestIsComplete(buildMatchRequest(runtime.matcher.answers))) await submitMatch();
        else renderMatcher();
      }
      else if (runtime.page.route === "browse") await renderBrowse();
      else if (runtime.page.route === "listing") {
        const identifier = runtime.page.listing_id || runtime.page.slug;
        await localizeRecommendationContext();
        await loadListing(identifier, Boolean(runtime.page.slug && !runtime.page.listing_id));
      }
      if (withFocus) focusMain();
    } catch (error) {
      renderFailure(error);
    }
  }

  async function boot() {
    runtime.page = Object.assign(routeFromLocation(), parsePageState());
    const saved = sessionPayload();
    runtime.lang = saved.lang === "en" ? "en" : "ar";
    runtime.matcher = initialMatcherState(saved.matcher);
    runtime.request = saved.request || null;
    runtime.listingRequest = saved.listing_request && typeof saved.listing_request === "object" ? saved.listing_request : {};
    runtime.recommendationContext = safeRecommendationContext(saved.recommendation_context || {}, saved.recommendation_context && saved.recommendation_context.lang);
    applyLocationSearch();
    document.documentElement.lang = runtime.lang;
    document.documentElement.dir = runtime.lang === "ar" ? "rtl" : "ltr";
    applyShellCopy();
    document.getElementById("language-switch").addEventListener("click", function () {
      setLanguage(runtime.lang === "ar" ? "en" : "ar");
    });
    window.addEventListener("popstate", function () {
      runtime.page = routeFromLocation();
      applyLocationSearch();
      loadRoute(true);
    });
    runtime.booted = true;
    loadingView();
    try {
      await loadConfig();
      await loadRoute(false);
    } catch (error) {
      renderFailure(error);
    }
  }

  return {
    COPY: COPY,
    approvedIncluded: approvedIncluded,
    adjustedDateWindow: adjustedDateWindow,
    answerStep: answerStep,
    boot: boot,
    buildMatchRequest: buildMatchRequest,
    buildSteps: buildSteps,
    canonicalListingRequest: canonicalListingRequest,
    chooseSessionToken: chooseSessionToken,
    contactState: contactState,
    focusQuestion: focusQuestion,
    goBack: goBack,
    initialMatcherState: initialMatcherState,
    listingQuoteRequest: listingQuoteRequest,
    optionIsSelected: optionIsSelected,
    parseLocationSearch: parseLocationSearch,
    publicAvailabilityStatus: publicAvailabilityStatus,
    rankedImpressionIds: rankedImpressionIds,
    responseWindowMessage: responseWindowMessage,
    retrySessionOperation: retrySessionOperation,
    safeRecommendationContext: safeRecommendationContext,
    safeImageUrl: safeImageUrl,
    safeWhatsAppUrl: safeWhatsAppUrl,
    setLanguage: setLanguage
  };
});
