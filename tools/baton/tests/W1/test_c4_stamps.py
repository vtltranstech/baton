"""Architecture stamps (contracts/versioning.md section 3): kept across `baton c4`, ignored by --check."""

from __future__ import annotations

from baton.graph.c4 import drift
from baton.graph.stamps import Stamp, apply, changelog, extract, promote, strip, tagged

BEFORE = """workspace "P" "p" {
    model {
        product = softwareSystem "P" "p" {
            orderService = container "order-service" "Orders" "Spring Boot"
            db = container "datastore" "collections: orders" "MongoDB" {
                tags "Database"
            }
        }
        orderService -> db "orders" "Mongo"
    }
}
"""

AFTER = """workspace "P" "p" {
    model {
        product = softwareSystem "P" "p" {
            orderService = container "order-service" "Orders and discounts" "Spring Boot"
            pricingJob = container "pricing-job" "Prices" "Spring Batch"
            db = container "datastore" "collections: orders" "MongoDB" {
                tags "Database"
            }
        }
        pricingJob -> db "prices" "Mongo"
    }
}
"""


def test_promote_stamps_new_and_changed_and_lists_removed():
    result = promote(BEFORE, AFTER, "S-010", "F-002", "2026-11-05")
    assert result.added_elements == ["pricingJob"]
    assert result.added_relationships == ['pricingJob -> db "prices"']
    assert result.changed == ["orderService"]
    assert result.removed == ['orderService -> db "orders"']
    stamps = extract(result.dsl)
    assert stamps["pricingJob"].tags == ["F-002"]
    assert stamps["pricingJob"].props == {
        "baton.story": "S-010", "baton.feature": "F-002", "baton.since": "2026-11-05"
    }
    assert stamps["orderService"].props == {"baton.changed-by": "S-010"}
    assert "db" not in stamps


def test_stamped_block_has_the_contract_shape():
    dsl = promote(BEFORE, AFTER, "S-010", "F-002", "2026-11-05").dsl
    assert (
        '            pricingJob = container "pricing-job" "Prices" "Spring Batch" {\n'
        '                tags "F-002"\n'
        "                properties {\n"
        '                    "baton.story" "S-010"\n'
        '                    "baton.feature" "F-002"\n'
        '                    "baton.since" "2026-11-05"\n'
        "                }\n"
        "            }\n"
    ) in dsl
    assert '                tags "Database"\n' in dsl


def test_stamps_survive_regeneration_and_check_ignores_them():
    stamped = promote(BEFORE, AFTER, "S-010", "F-002", "2026-11-05").dsl
    assert strip(stamped) == AFTER
    assert drift(strip(stamped), AFTER) == []
    assert apply(AFTER, extract(stamped)) == stamped
    assert apply(AFTER, {}) == AFTER


def test_a_later_story_appends_changed_by_and_keeps_the_original():
    first = promote(BEFORE, AFTER, "S-010", "F-002", "2026-11-05").dsl
    later = AFTER.replace('"Prices" "Spring Batch"', '"Prices and discounts" "Spring Batch"')
    second = promote(first, later, "S-014", "F-003", "2026-11-09")
    stamp = extract(second.dsl)["pricingJob"]
    assert stamp.props["baton.story"] == "S-010"
    assert stamp.props["baton.changed-by"] == "S-014"
    assert stamp.tags == ["F-002", "F-003"]
    latest = later.replace("Prices and discounts", "Prices, discounts")
    third = promote(second.dsl, latest, "S-020", "F-003", "x")
    assert extract(third.dsl)["pricingJob"].props["baton.changed-by"] == "S-014,S-020"


def test_one_line_properties_are_read():
    dsl = AFTER.replace(
        '        pricingJob -> db "prices" "Mongo"\n',
        '        pricingJob -> db "prices" "Mongo" {\n'
        '            tags "F-002"\n'
        '            properties { "baton.story" "S-010" "baton.changed-by" "S-014" }\n'
        "        }\n",
    )
    stamp = extract(dsl)['pricingJob -> db "prices"']
    assert stamp.props == {"baton.story": "S-010", "baton.changed-by": "S-014"}
    assert strip(dsl) == AFTER
    assert tagged(dsl, "F-002") == ['pricingJob -> db "prices"']


def test_changelog_appends_a_row_and_removals():
    result = promote(BEFORE, AFTER, "S-010", "F-002", "2026-11-05")
    text = changelog(None, "2026-11-05", "F-002", "S-010", result)
    assert (
        "| 2026-11-05 | F-002 | S-010 | +1 elements | +1 relationships | ~1 changed | 1 removed "
        "| changes/S-010.md |"
    ) in text
    assert '| 2026-11-05 | orderService -> db "orders" | removed-by S-010 |' in text
    unchanged = promote(result.dsl, result.dsl, "S-011", "F-002", "x")
    again = changelog(text, "2026-11-06", "F-002", "S-011", unchanged)
    rows = [line for line in again.splitlines() if line.startswith("| 2026")]
    assert [row.split(" | ")[2] for row in rows[:2]] == ["S-010", "S-011"]
    assert again.index("S-011") < again.index("## Removed")


def test_first_promotion_without_a_recorded_model_stamps_nothing():
    result = promote(None, AFTER, "S-010", "F-002", "2026-11-05")
    assert result.dsl == AFTER and not result.added_elements


def test_stamp_render_order():
    stamp = Stamp(["F-1"], {"baton.since": "d", "baton.story": "S-1"})
    assert extract(apply(AFTER, {"db": stamp}))["db"].props == {"baton.since": "d", "baton.story": "S-1"}
