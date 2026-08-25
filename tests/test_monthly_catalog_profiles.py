import json
import unittest


from monthly_public.catalog_profiles import (
    CatalogContractError,
    apply_approved_profile,
    build_prefill,
    completion,
    parse_coordinates,
    parse_global_settings,
    parse_place,
    parse_profile,
)


def valid_profile(**overrides):
    value = {
        "active": True,
        "name_ar": "عوجا | بيت بغرفتين في الملقا",
        "name_en": "Ouja | Two-bedroom home in Al Malqa",
        "short_ar": "بيت هادئ بغرفتين ومساحة عمل.",
        "short_en": "A quiet two-bedroom home with a workspace.",
        "content_verified": True,
        "structured": {
            "tagline_ar": "هدوء عملي في الملقا",
            "tagline_en": "A calm Al Malqa stay",
            "sections": [
                {
                    "title_ar": "المساحة",
                    "title_en": "The space",
                    "body_ar": "غرفتان تتسعان لأربعة مقيمين.",
                    "body_en": "Two bedrooms for up to four residents.",
                }
            ],
        },
        "neighborhood": "al_malqa",
        "neighborhood_ar": "الملقا",
        "neighborhood_en": "Al Malqa",
        "neighborhood_verified": True,
        "bedrooms": 2,
        "beds_count": 3,
        "baths": 2,
        "capacity": 4,
        "floor_area_sqm": 135,
        "images": [
            "https://images.example.test/1.jpg",
            "https://images.example.test/2.jpg",
            "https://images.example.test/3.jpg",
        ],
        "facts": {
            "parking": True,
            "elevator": None,
            "workspace": True,
        },
        "licence": {"licence_no": "AD-1001", "expires": "2027-08-25"},
        "commercial_terms": {
            "utilities": {
                "mode": "variable",
                "label_ar": "الكهرباء والماء حسب الاستهلاك.",
                "label_en": "Electricity and water are charged by use.",
            },
            "cleaning": {
                "mode": "optional",
                "amount_sar": 300,
                "label_ar": "تنظيف إضافي اختياري.",
                "label_en": "Optional additional cleaning.",
            },
        },
        "coordinates": {
            "lat": 24.802,
            "lng": 46.623,
            "source": "hostaway_listing",
            "verified": True,
        },
    }
    value.update(overrides)
    return value


def valid_settings():
    return {
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
                "refund_en": "Refunded after inspection under the confirmed terms.",
            },
            "payment_methods": [{"ar": "تحويل بنكي", "en": "Bank transfer"}],
        },
        "long_stay_route": "monthly_contract_review",
    }


class CatalogProfileContractTest(unittest.TestCase):
    def test_profile_normalizes_safe_bilingual_fields_and_three_state_facts(self):
        parsed = parse_profile(valid_profile())

        self.assertEqual(parsed["name_ar"], "عوجا | بيت بغرفتين في الملقا")
        self.assertEqual(parsed["facts"]["parking"], True)
        self.assertIsNone(parsed["facts"]["elevator"])
        self.assertEqual(parsed["commercial_terms"]["cleaning"]["amount_sar"], 300)

    def test_profile_rejects_unknown_or_source_owned_fields(self):
        for field in (
            "official_prices",
            "calendar",
            "rating",
            "reviews_count",
            "wifi_pass",
            "owner_phone",
        ):
            with self.subTest(field=field):
                with self.assertRaises(CatalogContractError) as caught:
                    parse_profile({field: "not allowed"})
                self.assertEqual(caught.exception.code, "unknown_field")

    def test_titles_require_their_expected_language(self):
        for value, field in (
            ({"name_ar": "English only"}, "name_ar"),
            ({"name_en": "عنوان عربي فقط"}, "name_en"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(CatalogContractError) as caught:
                    parse_profile(value)
                self.assertEqual(caught.exception.field, field)
                self.assertEqual(caught.exception.code, "language_mismatch")

    def test_optional_cleaning_requires_a_non_negative_sar_amount(self):
        terms = valid_profile()["commercial_terms"]
        terms["cleaning"].pop("amount_sar")
        with self.assertRaises(CatalogContractError) as caught:
            parse_profile({"commercial_terms": terms})
        self.assertEqual(caught.exception.field, "commercial_terms.cleaning.amount_sar")

    def test_duplicate_structured_sections_are_rejected(self):
        section = valid_profile()["structured"]["sections"][0]
        with self.assertRaises(CatalogContractError) as caught:
            parse_profile({"structured": {"sections": [section, dict(section)]}})
        self.assertEqual(caught.exception.code, "duplicate_section")

    def test_coordinates_accept_a_pair_or_maps_url_with_riyadh_bounds(self):
        pair = parse_coordinates("24.802, 46.623")
        maps = parse_coordinates("https://maps.google.com/maps?q=24.802,46.623")
        self.assertEqual((pair["lat"], pair["lng"]), (24.802, 46.623))
        self.assertEqual(maps["source"], "staff_maps_pin")
        self.assertTrue(maps["verified"])

        with self.assertRaises(CatalogContractError) as caught:
            parse_coordinates("21.4, 39.8")
        self.assertEqual(caught.exception.code, "outside_riyadh")

    def test_prefill_drops_sensitive_guide_and_operations_values(self):
        source = {
            "id": 101,
            "name": "Ouja | Unit 101",
            "lat": 24.80,
            "lng": 46.65,
            "wifi_pass": "secret-wifi",
            "door_code": "1234",
            "notes": "call 0500000000",
        }
        prefill = build_prefill(source, stay={}, licence=None, rating=None)
        rendered = json.dumps(prefill, ensure_ascii=False)
        for forbidden in (
            "secret-wifi",
            "1234",
            "0500000000",
            "wifi_pass",
            "door_code",
            "notes",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_hostaway_coordinates_prefill_as_verified(self):
        value = build_prefill(
            {"id": 101, "lat": 24.80, "lng": 46.65}, {}, None, None
        )
        self.assertEqual(value["coordinates"]["source"], "hostaway_listing")
        self.assertTrue(value["coordinates"]["verified"])
        self.assertEqual(value["sources"]["coordinates"], "hostaway_listing")

    def test_one_malformed_source_field_does_not_discard_valid_prefills(self):
        value = build_prefill(
            {"id": 101, "bedrooms": 2, "lat": 21.4, "lng": 39.8},
            {},
            None,
            None,
        )
        self.assertEqual(value["bedrooms"], 2)
        self.assertEqual(value["sources"]["bedrooms"], "hostaway_listing")
        self.assertNotIn("coordinates", value)

    def test_title_matched_guide_coordinates_are_never_prefilled_as_verified(self):
        value = build_prefill(
            {"id": 101},
            {"guide_coordinates": {"lat": 24.80, "lng": 46.65}},
            None,
            None,
        )
        self.assertFalse(value["coordinates"]["verified"])
        self.assertEqual(value["coordinates"]["source"], "guide_title_match")

    def test_prefill_precedence_is_draft_approved_stay_then_hostaway(self):
        value = build_prefill(
            {"id": 101, "bedrooms": 1},
            {"title_ar": "عنوان الإقامة", "bedrooms": 2},
            None,
            None,
            approved={"name_ar": "عنوان معتمد", "bedrooms": 3},
            draft={"name_ar": "عنوان مسودة"},
        )
        self.assertEqual(value["name_ar"], "عنوان مسودة")
        self.assertEqual(value["bedrooms"], 3)
        self.assertEqual(value["sources"]["name_ar"], "monthly_draft")
        self.assertEqual(value["sources"]["bedrooms"], "monthly_approved")

    def test_approved_profile_cannot_replace_engine_calendar_or_rating(self):
        base = {
            "id": 101,
            "official_prices": {"2026-09": {"monthly_rate_sar": 12000}},
            "calendar": {"synced_at": "2026-08-25T09:00:00+03:00"},
            "rating": 4.9,
        }
        merged = apply_approved_profile(base, parse_profile(valid_profile()))
        self.assertEqual(merged["official_prices"], base["official_prices"])
        self.assertEqual(merged["calendar"], base["calendar"])
        self.assertEqual(merged["rating"], 4.9)
        self.assertTrue(merged["content_verified"])

    def test_settings_and_destination_contracts_are_strict(self):
        settings = parse_global_settings(valid_settings())
        self.assertEqual(settings["whatsapp_number"], "966500000000")
        with self.assertRaises(CatalogContractError):
            parse_global_settings({**valid_settings(), "MONTHLY_SESSION_SECRET": "no"})

        place = parse_place(
            {
                "label_ar": "مستشفى الملك فيصل",
                "label_en": "King Faisal Specialist Hospital",
                "purposes": ["treatment", "visit"],
                "coordinates": "24.672,46.680",
                "source_note": "Pin reviewed by operations",
            }
        )
        self.assertEqual(place["kind"], "destination")
        self.assertEqual(place["purposes"], ["treatment", "visit"])
        self.assertNotIn("lat", json.dumps({"public": place["label_ar"]}))

    def test_destination_accepts_strict_staff_verification_metadata(self):
        from monthly_public.catalog_profiles import parse_place

        place = parse_place(
            {
                "label_ar": "مركز الملك عبدالله المالي",
                "label_en": "King Abdullah Financial District",
                "purposes": ["work"],
                "coordinates": {
                    "lat": 24.7656964,
                    "lng": 46.6407087,
                    "source": "priority_places_2026_08_25",
                    "verified": True,
                },
                "source_note": "موقع رسمي + OpenStreetMap",
                "category_id": "business_hubs",
                "category_ar": "مراكز الأعمال والتوظيف",
                "category_en": "Business & employment hubs",
                "priority": 1,
                "address_ar": "العقيق، الرياض",
                "address_en": "Al Aqiq, Riyadh",
                "district_ar": "العقيق",
                "district_en": "Al Aqiq",
                "map_url": "https://www.google.com/maps/search/?api=1&query=24.7656964%2C46.6407087",
                "official_source_url": "https://www.kafd.sa/en/faq/",
                "coordinate_source_url": "https://www.openstreetmap.org/way/1220645868",
                "verified_at": "2026-08-25",
                "review_interval_ar": "سنوي",
                "reason_ar": "مركز أعمال رئيسي.",
                "operations_note_ar": "نقطة مركزية موثقة.",
            }
        )

        self.assertEqual(place["category_id"], "business_hubs")
        self.assertEqual(place["priority"], 1)
        self.assertEqual(place["verified_at"], "2026-08-25")

    def test_completion_separates_required_fields_from_non_blocking_proof(self):
        ready = completion(parse_profile(valid_profile()))
        self.assertTrue(ready["ready_for_approval"])
        self.assertEqual(ready["staff_blockers"], [])

        incomplete = valid_profile()
        incomplete.pop("licence")
        incomplete.pop("coordinates")
        status = completion(parse_profile(incomplete))
        self.assertFalse(status["ready_for_approval"])
        self.assertIn("licence_missing", status["staff_blockers"])
        self.assertIn("coordinates_unverified", status["warnings"])


if __name__ == "__main__":
    unittest.main()
