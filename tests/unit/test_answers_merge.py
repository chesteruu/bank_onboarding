from onboarding.domain.answers import merge_step_answers


def test_no_collision_is_plain_merge():
    merged = merge_step_answers(
        [
            ("identity", {"national_id": "199001011234", "full_name": "Anna"}),
            ("contact", {"email": "anna@example.com"}),
        ]
    )
    assert merged == {
        "national_id": "199001011234",
        "full_name": "Anna",
        "email": "anna@example.com",
    }


def test_collision_preserves_both_values_namespaced():
    merged = merge_step_answers(
        [
            ("identity", {"national_id": "199001011234"}),
            ("signatory", {"national_id": "770101-5566"}),
        ]
    )
    # Last-write-wins flat value is preserved for backward compatibility.
    assert merged["national_id"] == "770101-5566"
    # No value is silently lost: both are available namespaced by step.
    assert merged["identity.national_id"] == "199001011234"
    assert merged["signatory.national_id"] == "770101-5566"


def test_same_value_across_steps_does_not_namespace():
    merged = merge_step_answers(
        [
            ("a", {"tax_residency": "SE"}),
            ("b", {"tax_residency": "SE"}),
        ]
    )
    assert merged == {"tax_residency": "SE"}


def test_repeated_step_key_overwrites_without_namespacing():
    # Resubmitting the same step (go back + resubmit) should just overwrite.
    merged = merge_step_answers(
        [
            ("identity", {"national_id": "111"}),
            ("identity", {"national_id": "222"}),
        ]
    )
    assert merged == {"national_id": "222"}
