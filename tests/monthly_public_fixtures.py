import copy
import datetime as dt

from monthly_public.settings import load_settings


NOW = dt.datetime(2026, 8, 25, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))


def valid_settings():
    return load_settings(
        {
            "whatsapp_number": "966500000000",
            "working_hours": {
                "timezone": "Asia/Riyadh",
                "schedule": {
                    "sunday": [["09:00", "18:00"]],
                    "monday": [["09:00", "18:00"]],
                    "tuesday": [["09:00", "18:00"]],
                    "wednesday": [["09:00", "18:00"]],
                    "thursday": [["09:00", "18:00"]],
                },
            },
            "commercial_terms": {
                "included": ["internet", "maintenance"],
                "deposit": {
                    "amount_sar": 2000,
                    "refund_ar": "يُسترد بعد فحص الشقة حسب الشروط المؤكدة.",
                    "refund_en": "Refunded after checkout inspection under the confirmed terms.",
                },
                "payment_methods": [
                    {"ar": "تحويل بنكي", "en": "Bank transfer"},
                    {"ar": "بطاقة", "en": "Card"},
                ],
            },
            "long_stay_route": "monthly_contract_review",
        }
    )


def valid_listing(**overrides):
    listing = {
        "id": 1001,
        "active": True,
        "slug": "ouja-al-malqa-1001",
        "name_ar": "عوجا | بيت بغرفتين في الملقا",
        "name_en": "Ouja | Two-bedroom home in Al Malqa",
        "short_ar": "بيت هادئ بغرفتين ومساحة عمل.",
        "short_en": "A quiet two-bedroom home with a workspace.",
        "desc_ar": "وصف خام لا يجب عرضه.",
        "desc_en": "Raw description that must not render.",
        "structured": {
            "tagline_ar": "هدوء عملي في الملقا",
            "tagline_en": "A calm, practical Al Malqa stay",
            "emblems": [
                {"icon": "wifi", "ar": "إنترنت", "en": "Internet"},
            ],
            "sections": [
                {
                    "title_ar": "المساحة",
                    "title_en": "The space",
                    "body_ar": "غرفتا نوم تتسعان لأربعة مقيمين.",
                    "body_en": "Two bedrooms for up to four residents.",
                },
                {
                    "title_ar": "العمل",
                    "title_en": "Work ready",
                    "body_ar": "توجد مساحة عمل موثقة داخل البيت.",
                    "body_en": "The home has a verified workspace.",
                },
            ],
            "neighborhood_ar": "في حي الملقا.",
            "neighborhood_en": "In Al Malqa.",
        },
        "content_verified": True,
        "neighborhood": "al_malqa",
        "neighborhood_ar": "الملقا",
        "neighborhood_en": "Al Malqa",
        "neighborhood_verified": True,
        "bedrooms": 2,
        "beds": 2,
        "beds_count": 3,
        "baths": 2,
        "capacity": 4,
        "floor_area_sqm": 135,
        "images": [
            "https://images.example.test/1001-1.jpg",
            "https://images.example.test/1001-2.jpg",
            "https://images.example.test/1001-3.jpg",
            "https://images.example.test/1001-4.jpg",
        ],
        "amenities": [
            "Wireless",
            "Internet",
            "Kitchen",
            "Free parking",
            "Workspace",
        ],
        "facts": {"workspace": True, "parking": True},
        "rating": 4.82,
        "reviews_count": 34,
        "rating_verified": True,
        "rating_source": "approved_public_reviews",
        "licence": {
            "licence_no": "TEST-AD-1001",
            "expires": "2027-08-25",
            "entered_by": "test",
            "updated_at": "2026-08-25T09:00:00+03:00",
        },
        "official_prices": {
            "2026-09": {
                "monthly_rate_sar": 12000,
                "currency": "SAR",
                "source": "engine_verified",
                "verified_at": "2026-08-25T09:30:00+03:00",
            }
        },
        "calendar": {
            "synced_at": "2026-08-25T09:40:00+03:00",
            "from": "2026-08-25",
            "to": "2027-03-23",
            "blocked_dates": [],
        },
        "commercial_terms": {
            "utilities": {
                "mode": "variable",
                "label_ar": "الكهرباء والماء حسب الاستهلاك.",
                "label_en": "Electricity and water are charged by use.",
            },
            "cleaning": {
                "mode": "optional",
                "amount_sar": 300,
                "label_ar": "تنظيف إضافي اختياري بقيمة 300 ر.س.",
                "label_en": "Optional additional cleaning for SAR 300.",
            },
        },
        "coordinates": {
            "lat": 24.802,
            "lng": 46.623,
            "verified": True,
            "source": "approved_listing_coordinates",
        },
    }
    listing.update(copy.deepcopy(overrides))
    return listing
