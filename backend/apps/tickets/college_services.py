import csv
import io

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.events.models import Event

from .models import CollegeStudentTicket, CollegeStudentTicketSequence


class CollegeTicketConflict(APIException):
    status_code = 409
    default_detail = "The college student ticket conflicts with an existing record."
    default_code = "COLLEGE_TICKET_CONFLICT"


def _clean_student(*, student_name, student_email):
    name = str(student_name or "").strip()
    email = str(student_email or "").strip().lower()
    if not name:
        raise ValidationError({"student_name": "Student name is required."})
    if len(name) > 200:
        raise ValidationError({"student_name": "Student name must be at most 200 characters."})
    try:
        validate_email(email)
    except ValidationError as error:
        raise ValidationError({"student_email": "Enter a valid student email address."}) from error
    if len(email) > 254:
        raise ValidationError({"student_email": "Student email must be at most 254 characters."})
    return name, email


def _next_college_ticket_code(event):
    year = timezone.localtime(event.start_at).year
    CollegeStudentTicketSequence.objects.get_or_create(year=year)
    sequence = CollegeStudentTicketSequence.objects.select_for_update().get(year=year)
    prefix = settings.COLLEGE_TICKET_ID_PREFIX
    ticket_code = f"{prefix}-{year}-SIMS{sequence.next_number:03d}"
    sequence.next_number += 1
    sequence.save(update_fields=("next_number",))
    return ticket_code


@transaction.atomic
def create_college_student_ticket(
    *,
    event,
    student_name,
    student_email,
    created_by=None,
    email_delivery_enabled=False,
):
    name, email = _clean_student(
        student_name=student_name,
        student_email=student_email,
    )
    try:
        ticket = CollegeStudentTicket.objects.create(
            event=event,
            student_name=name,
            student_email=email,
            ticket_code=_next_college_ticket_code(event),
            email_delivery_enabled=False,
            created_by=created_by,
        )
        return ticket
    except IntegrityError as error:
        raise CollegeTicketConflict(
            "A college-student ticket already exists for this event and email address."
        ) from error


def _validated_import_rows(*, event, rows):
    seen = set()
    existing = set(
        CollegeStudentTicket.objects.filter(event=event).values_list(
            "student_email", flat=True
        )
    )
    results = []
    for row_number, row in enumerate(rows, start=2):
        try:
            name, email = _clean_student(
                student_name=row.get("student_name"),
                student_email=row.get("student_email"),
            )
            if email in seen:
                raise ValidationError(
                    {"student_email": "This email is duplicated within the import file."}
                )
            if email in existing:
                raise ValidationError(
                    {"student_email": "A college-student ticket already exists for this event."}
                )
            seen.add(email)
            results.append(
                {"row": row_number, "valid": True, "student_name": name, "student_email": email}
            )
        except (AttributeError, ValidationError) as error:
            detail = error.message_dict if hasattr(error, "message_dict") else {
                "row": "Each row must contain student_name and student_email."
            }
            results.append({"row": row_number, "valid": False, "errors": detail})
    return results


def bulk_create_college_student_tickets(
    *,
    event,
    rows,
    created_by=None,
    email_delivery_enabled=False,
    dry_run=False,
    max_rows=500,
):
    rows = list(rows)
    if not rows:
        raise ValidationError({"file": "The CSV must contain at least one student row."})
    if len(rows) > max_rows:
        raise ValidationError({"file": f"Import is limited to {max_rows} student rows."})
    validated = _validated_import_rows(event=event, rows=rows)
    invalid_rows = [item for item in validated if not item["valid"]]
    if invalid_rows or dry_run:
        return {
            "created": [],
            "rows": validated,
            "valid_count": len(validated) - len(invalid_rows),
            "error_count": len(invalid_rows),
            "dry_run": dry_run,
        }

    created = []
    try:
        with transaction.atomic():
            for item in validated:
                created.append(
                    create_college_student_ticket(
                        event=event,
                        student_name=item["student_name"],
                        student_email=item["student_email"],
                        created_by=created_by,
                        email_delivery_enabled=False,
                    )
                )
    except CollegeTicketConflict as error:
        raise CollegeTicketConflict(
            "A student in this import was created concurrently; no rows were imported."
        ) from error
    return {
        "created": created,
        "rows": [
            {
                "row": item["row"],
                "valid": True,
                "ticket_code": created[index].ticket_code,
            }
            for index, item in enumerate(validated)
        ],
        "valid_count": len(created),
        "error_count": 0,
        "dry_run": False,
    }


def parse_college_student_csv(content):
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValidationError({"file": "Upload a UTF-8 CSV file."}) from error
    required_headers = {"student_name", "student_email"}
    if not reader.fieldnames:
        raise ValidationError(
            {"file": "CSV headers must include student_name and student_email."}
        )
    normalized_headers = [header.strip() for header in reader.fieldnames]
    if not required_headers.issubset(normalized_headers):
        raise ValidationError(
            {"file": "CSV headers must include student_name and student_email."}
        )
    return [
        {
            normalized_headers[index]: row.get(raw_header)
            for index, raw_header in enumerate(reader.fieldnames)
        }
        for row in reader
    ]
