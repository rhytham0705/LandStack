"""
LandStack - Land Record Validation Engine

Responsibilities:
1. Validate extracted land-record fields.
2. Apply business rules.
3. Detect duplicate records.
4. Calculate per-field confidence.
5. Flag uncertain fields for human review.

This is a prototype implementation.
Production integrations with LRMS/DILRMP/GIS can be added later.
"""

import re
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

# Fields expected from the extraction/OCR module
EXPECTED_FIELDS = [
    "landowner_name",
    "survey_number",
    "khasra_number",
    "khata_number",
    "plot_area",
    "village",
    "tehsil",
    "district",
    "land_classification",
    "ownership_details",
    "mutation_records",
    "registration_information",
]

# Any field below this confidence is sent for human review
LOW_CONFIDENCE_THRESHOLD = 0.70

# Confidence below this value is considered very uncertain
VERY_LOW_CONFIDENCE_THRESHOLD = 0.50


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def normalize_text(value: Any) -> str:
    """Normalize text for comparison."""

    if value is None:
        return ""

    value = str(value).strip().lower()

    # Remove extra spaces
    value = re.sub(r"\s+", " ", value)

    return value


def normalize_identifier(value: Any) -> str:
    """
    Normalize survey/khasra/khata numbers.

    Example:
        ' 12 / A ' -> '12/a'
        'K-123'    -> 'k123'
    """

    if value is None:
        return ""

    value = str(value).strip().lower()

    value = re.sub(r"\s+", "", value)

    return value


def is_missing(value: Any) -> bool:
    """Check whether an extracted value is empty."""

    if value is None:
        return True

    if isinstance(value, str) and not value.strip():
        return True

    return False


# ---------------------------------------------------------
# Individual field validators
# ---------------------------------------------------------

def validate_registration(registration):
    issues = []

    if not registration:
        return ["Registration information missing"]

    number = registration.get("registration_number")

    if number and not re.match(r"^[A-Za-z0-9/-]+$", number):
        issues.append("Invalid registration number format")
    return issues

def validate_owner_name(value: Any) -> List[str]:
    issues = []

    if is_missing(value):
        issues.append("Landowner name is missing")
        return issues

    value = str(value).strip()

    # Basic name validation
    if len(value) < 2:
        issues.append("Landowner name is too short")

    if re.search(r"\d", value):
        issues.append("Landowner name contains numbers")

    return issues


def validate_identifier(value: Any, field_name: str) -> List[str]:
    issues = []

    if is_missing(value):
        issues.append(f"{field_name} is missing")
        return issues

    value = str(value).strip()

    if len(value) > 50:
        issues.append(f"{field_name} is unusually long")

    # Allow numbers, letters, slash, dash and spaces
    if not re.match(r"^[A-Za-z0-9./\-\s]+$", value):
        issues.append(f"{field_name} contains invalid characters")

    return issues


def validate_plot_area(value: Any) -> List[str]:
    issues = []

    if is_missing(value):
        issues.append("Plot area is missing")
        return issues

    value_str = str(value).lower().strip()

    # Try to extract numerical area
    match = re.search(r"(\d+(?:\.\d+)?)", value_str)

    if not match:
        issues.append("Plot area does not contain a valid number")
        return issues

    area = float(match.group(1))

    if area <= 0:
        issues.append("Plot area must be greater than zero")

    # Prototype sanity check
    if area > 1_000_000:
        issues.append("Plot area is unusually large")

    return issues


def validate_location(value: Any, field_name: str) -> List[str]:
    issues = []

    if is_missing(value):
        issues.append(f"{field_name} is missing")
        return issues

    value = str(value).strip()

    if len(value) < 2:
        issues.append(f"{field_name} is too short")

    if re.search(r"\d", value):
        issues.append(f"{field_name} contains numbers")

    return issues


# ---------------------------------------------------------
# Business rule validation
# ---------------------------------------------------------

def validate_business_rules(record: Dict[str, Any]) -> List[str]:
    """
    Apply cross-field/business-rule checks.

    These are prototype rules. Actual state-specific land
    record rules can be added later.
    """

    errors = []

    survey = normalize_identifier(record.get("survey_number"))
    khasra = normalize_identifier(record.get("khasra_number"))
    khata = normalize_identifier(record.get("khata_number"))

    village = normalize_text(record.get("village"))
    tehsil = normalize_text(record.get("tehsil"))
    district = normalize_text(record.get("district"))

    # Rule 1: At least one land identifier should exist
    if not survey and not khasra and not khata:
        errors.append(
            "No survey, khasra or khata identifier is available"
        )

    # Rule 2: Location hierarchy should be present
    if village and not tehsil:
        errors.append(
            "Village is present but tehsil is missing"
        )

    if tehsil and not district:
        errors.append(
            "Tehsil is present but district is missing"
        )

    # Rule 3: Owner should exist for an ownership record
    ownership = record.get("ownership_details")

    if ownership and is_missing(record.get("landowner_name")):
        errors.append(
            "Ownership information exists but landowner name is missing"
        )

    # Rule 4: Plot area should exist for a land parcel
    if (
        (survey or khasra)
        and is_missing(record.get("plot_area"))
    ):
        errors.append(
            "Land identifier exists but plot area is missing"
        )

    return errors


# ---------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------

def calculate_field_confidence(
    field_name: str,
    value: Any,
    extraction_confidence: Optional[float] = None,
    issues: Optional[List[str]] = None,
) -> float:
    """
    Calculate confidence for an individual field.

    If OCR/extraction already supplied confidence, use it as
    the base score and adjust it according to validation issues.
    """

    issues = issues or []

    # Base confidence
    if extraction_confidence is not None:
        try:
            confidence = float(extraction_confidence)
        except (ValueError, TypeError):
            confidence = 0.80
    else:
        # Prototype default confidence
        confidence = 0.85 if not is_missing(value) else 0.20

    confidence = max(0.0, min(1.0, confidence))

    # Missing fields receive very low confidence
    if is_missing(value):
        return 0.15

    # Penalize validation problems
    for issue in issues:
        issue_lower = issue.lower()

        if "missing" in issue_lower:
            confidence -= 0.40

        elif "invalid" in issue_lower:
            confidence -= 0.25

        elif "unusually" in issue_lower:
            confidence -= 0.15

        elif "contains" in issue_lower:
            confidence -= 0.15

        else:
            confidence -= 0.10

    confidence = max(0.0, min(1.0, confidence))

    return round(confidence, 2)


# ---------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------

def create_record_key(record: Dict[str, Any]) -> str:
    """
    Generate a comparison key for a land record.

    The combination of location + survey/khasra/khata is
    useful for prototype duplicate detection.
    """

    district = normalize_text(record.get("district"))
    tehsil = normalize_text(record.get("tehsil"))
    village = normalize_text(record.get("village"))

    survey = normalize_identifier(record.get("survey_number"))
    khasra = normalize_identifier(record.get("khasra_number"))
    khata = normalize_identifier(record.get("khata_number"))

    return "|".join([
        district,
        tehsil,
        village,
        survey,
        khasra,
        khata,
    ])


def detect_duplicate(
    record: Dict[str, Any],
    existing_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compare the new record with existing database records.

    Returns duplicate status and matching record IDs.
    """

    new_key = create_record_key(record)

    if not new_key.replace("|", ""):
        return {
            "is_duplicate": False,
            "matching_records": [],
        }

    matches = []

    for existing in existing_records:

        existing_key = create_record_key(existing)

        if existing_key == new_key:
            record_id = existing.get("id")

            matches.append(record_id)

    return {
        "is_duplicate": len(matches) > 0,
        "matching_records": matches,
    }


# ---------------------------------------------------------
# Field validation dispatcher
# ---------------------------------------------------------

def validate_field(field_name: str, value: Any) -> List[str]:
    """Select the correct validation rules for each field."""

    if field_name == "landowner_name":
        return validate_owner_name(value)

    if field_name in [
        "survey_number",
        "khasra_number",
        "khata_number",
    ]:
        return validate_identifier(value, field_name)

    if field_name == "plot_area":
        return validate_plot_area(value)

    if field_name in [
        "village",
        "tehsil",
        "district",
    ]:
        return validate_location(value, field_name)

    # Optional fields
    if field_name in [
        "mutation_records",
        "registration_information",
        "land_classification",
        "ownership_details",
    ]:
        if is_missing(value):
            return []

    return []


# ---------------------------------------------------------
# Main validation function
# ---------------------------------------------------------

def validate_record(
    record: Dict[str, Any],
    existing_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Main entry point.

    Parameters
    ----------
    record:
        Extracted land record.

    existing_records:
        Records already present in the database.

    Returns
    -------
    Dict containing:
        - field-level validation
        - confidence scores
        - business-rule errors
        - duplicate status
        - overall status
    """

    existing_records = existing_records or []

    field_results = {}

    # ---------------------------------------------
    # Validate individual fields
    # ---------------------------------------------

    for field_name in EXPECTED_FIELDS:

        value = record.get(field_name)

        # Extraction module may provide confidence
        extraction_confidence = None

        confidence_data = record.get("_confidence", {})

        if isinstance(confidence_data, dict):
            extraction_confidence = confidence_data.get(field_name)

        issues = validate_field(field_name, value)

        confidence = calculate_field_confidence(
            field_name,
            value,
            extraction_confidence,
            issues,
        )

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            status = "REVIEW"
        else:
            status = "VALID"

        field_results[field_name] = {
            "value": value,
            "confidence": confidence,
            "status": status,
            "issues": issues,
        }

    # ---------------------------------------------
    # Business rules
    # ---------------------------------------------

    business_rule_errors = validate_business_rules(record)

    # ---------------------------------------------
    # Duplicate detection
    # ---------------------------------------------

    duplicate_result = detect_duplicate(
        record,
        existing_records,
    )

    # ---------------------------------------------
    # Calculate overall confidence
    # ---------------------------------------------

    confidence_values = [
        result["confidence"]
        for result in field_results.values()
        if result["value"] is not None
    ]

    if confidence_values:
        overall_confidence = round(
            sum(confidence_values) / len(confidence_values),
            2,
        )
    else:
        overall_confidence = 0.0

    # ---------------------------------------------
    # Find fields requiring human review
    # ---------------------------------------------

    review_fields = [
        field_name
        for field_name, result in field_results.items()
        if result["status"] == "REVIEW"
    ]

    # ---------------------------------------------
    # Determine final status
    # ---------------------------------------------

    if duplicate_result["is_duplicate"]:
        overall_status = "DUPLICATE"

    elif business_rule_errors:
        overall_status = "REVIEW_REQUIRED"

    elif review_fields:
        overall_status = "REVIEW_REQUIRED"

    else:
        overall_status = "VALIDATED"

    # ---------------------------------------------
    # Return complete validation result
    # ---------------------------------------------

    return {
        "overall_status": overall_status,
        "overall_confidence": overall_confidence,

        "fields": field_results,

        "business_rule_errors": business_rule_errors,

        "duplicate": duplicate_result,

        "review_required": len(review_fields) > 0
            or len(business_rule_errors) > 0
            or duplicate_result["is_duplicate"],

        "review_fields": review_fields,
    }


# ---------------------------------------------------------
# Example / local testing
# ---------------------------------------------------------

if __name__ == "__main__":
'''
    sample_record = {
        "landowner_name": "Ramesh Kumar",
        "survey_number": "12/A",
        "khasra_number": "123",
        "khata_number": "45",
        "plot_area": "1250 sq ft",
        "village": "Rampur",
        "tehsil": "Abhanpur",
        "district": "Raipur",
        "land_classification": "Agricultural",
        "ownership_details": "Individual",
        "mutation_records": None,
        "registration_information": None,

        # Optional confidence received from OCR
        "_confidence": {
            "landowner_name": 0.96,
            "survey_number": 0.93,
            "khasra_number": 0.91,
            "khata_number": 0.89,
            "plot_area": 0.62,
            "village": 0.97,
            "tehsil": 0.94,
            "district": 0.98,
            "land_classification": 0.91,
            "ownership_details": 0.88,
        },
    }

    existing_records = [
        {
            "id": 1,
            "landowner_name": "Suresh Kumar",
            "survey_number": "10",
            "khasra_number": "101",
            "khata_number": "30",
            "village": "Rampur",
            "tehsil": "Abhanpur",
            "district": "Raipur",
        }
    ]
'''
    result = validate_record(
        sample_record,
        existing_records,
    )

    import json

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )
