from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class TicketQr(Flowable):
    def __init__(self, token, size=35 * mm):
        super().__init__()
        self.token = token
        self.width = size
        self.height = size

    def draw(self):
        qr = QrCodeWidget(self.token)
        qr.barWidth = self.width
        qr.barHeight = self.height
        drawing = Drawing(self.width, self.height)
        drawing.add(qr)
        renderPDF.draw(drawing, self.canv, 0, 0)


def _ticket_image(filename, *, width, height):
    image_path = Path(settings.REPOSITORY_ROOT) / "client" / "public" / filename
    return Image(str(image_path), width=width, height=height, kind="bound")


def _event_datetime(event):
    local_start = timezone.localtime(event.start_at)
    local_end = timezone.localtime(event.end_at)
    event_date = local_start.strftime("%d %B %Y")
    event_time = (
        f"{local_start.strftime('%I:%M %p').lstrip('0')} – "
        f"{local_end.strftime('%I:%M %p').lstrip('0')}"
    )
    return event_date, event_time


def generate_tickets_pdf(tickets):
    tickets = list(tickets)
    if not tickets:
        raise ValueError("A ticket PDF requires at least one ticket.")

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A5,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=f"Tickets for {tickets[0].registration.event.name}",
        pageCompression=0,
    )
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TicketTitle",
        parent=base_styles["Title"],
        alignment=TA_LEFT,
        textColor=colors.HexColor("#b71959"),
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        spaceAfter=1 * mm,
    )
    eyebrow_style = ParagraphStyle(
        "TicketEyebrow",
        parent=base_styles["BodyText"],
        textColor=colors.HexColor("#455276"),
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        spaceAfter=1 * mm,
    )
    section_style = ParagraphStyle(
        "TicketSection",
        parent=base_styles["BodyText"],
        textColor=colors.HexColor("#b71959"),
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        spaceBefore=1.2 * mm,
        spaceAfter=0.5 * mm,
    )
    value_style = ParagraphStyle(
        "TicketValue",
        parent=base_styles["BodyText"],
        textColor=colors.HexColor("#18264b"),
        fontSize=9,
        leading=12,
        wordWrap="CJK",
    )
    note_style = ParagraphStyle(
        "TicketNote",
        parent=value_style,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#455276"),
        fontSize=8,
    )
    terms_style = ParagraphStyle(
        "TicketTerms",
        parent=value_style,
        fontSize=6.5,
        leading=7.5,
        textColor=colors.HexColor("#455276"),
    )

    story = []
    for index, ticket in enumerate(tickets):
        registration = ticket.registration
        event = registration.event
        event_date, event_time = _event_datetime(event)

        header = Table(
            [[
                _ticket_image("sims-logo.png", width=17 * mm, height=17 * mm),
                [
                    Paragraph("SOUNDARYA INSTITUTE OF MANAGEMENT AND SCIENCE", eyebrow_style),
                    Paragraph(escape(event.name), title_style),
                    Paragraph("DAKSHA STUDENT COUNCIL · OFFICIAL ENTRY PASS", eyebrow_style),
                ],
            ]],
            colWidths=(21 * mm, 107 * mm),
        )
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        poster = _ticket_image(
            "dhandiya-night-poster.jpeg",
            width=49 * mm,
            height=82 * mm,
        )
        ticket_details = [
            Paragraph("EVENT DETAILS", section_style),
            Paragraph(f"<b>DATE</b><br/>{escape(event_date)}", value_style),
            Paragraph(f"<b>TIME</b><br/>{escape(event_time)}", value_style),
            Paragraph(
                f"<b>VENUE</b><br/>{escape(event.venue)} · {escape(event.city)}",
                value_style,
            ),
            Paragraph("ADMISSION", section_style),
            Paragraph(
                f"<b>Attendee</b><br/>{escape(ticket.attendee_name or registration.buyer_name)}",
                value_style,
            ),
            Paragraph(
                f"<b>Ticket type</b><br/>{escape(registration.ticket_tier.name)}",
                value_style,
            ),
            Paragraph(
                f"<b>Ticket ID</b><br/>{escape(ticket.ticket_code)}",
                value_style,
            ),
            Paragraph(
                f"<b>Registration ID</b><br/>{escape(registration.registration_code)}",
                value_style,
            ),
            Spacer(1, 2 * mm),
            TicketQr(ticket.token),
            Spacer(1, 1 * mm),
            Paragraph("Scan this QR code at the event entrance.", note_style),
        ]
        content = Table(
            [[poster, ticket_details]],
            colWidths=(53 * mm, 75 * mm),
        )
        content.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf0")),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#e7d9bc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 1.5 * mm),
                    ("RIGHTPADDING", (0, 0), (0, 0), 1 * mm),
                    ("TOPPADDING", (0, 0), (0, 0), 1.5 * mm),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 1.5 * mm),
                    ("LEFTPADDING", (1, 0), (1, 0), 2 * mm),
                    ("RIGHTPADDING", (1, 0), (1, 0), 2 * mm),
                    ("TOPPADDING", (1, 0), (1, 0), 1.5 * mm),
                    ("BOTTOMPADDING", (1, 0), (1, 0), 1.5 * mm),
                    ("LINEBEFORE", (1, 0), (1, 0), 0.6, colors.HexColor("#e7d9bc")),
                ]
            )
        )

        terms_content = [
            "<b>Terms &amp; Conditions</b>",
            "- Carry your ticket and valid ID. Arrive 1 hour early for entry and security checking.",
            "- Tickets are non-transferable and non-refundable. No re-entry after exit.",
            "- One pair of Dandiya sticks and refreshments are included with each ticket.",
            "- Traditional/ethnic wear is recommended.",
            "- Outside food, beverages, and water bottles are not allowed.",
            "- Alcohol, smoking, drugs, weapons, and sharp objects are strictly prohibited.",
            "- Security and bag checks will be conducted at the entrance.",
            "- The organizers reserve the right of admission and are not responsible for lost belongings.",
            "- Any misconduct or violation of rules may result in immediate eviction without refund.",
        ]
        terms = Table(
            [[
                Paragraph(
                    "<br/>".join(terms_content),
                    terms_style,
                )
            ]],
            colWidths=(128 * mm,),
        )
        terms.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff3d6")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#e7d9bc")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ]
            )
        )

        story.extend([header, Spacer(1, 4 * mm), content, Spacer(1, 2 * mm), terms])
        if index < len(tickets) - 1:
            story.append(PageBreak())

    document.build(story)
    return output.getvalue()


def generate_ticket_id_confirmation_pdf(registration):
    from .models import Payment

    payment = Payment.objects.filter(
        intent__registration=registration,
        provider=Payment.Provider.UPI_MANUAL,
    ).order_by("-submitted_at", "-created_at").first()
    if payment and payment.status == Payment.Status.PENDING_VERIFICATION:
        payment_status = "Pending Verification"
    elif payment:
        payment_status = payment.get_status_display()
    else:
        payment_status = "Pending Payment"
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A5,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=f"Ticket ID confirmation for {registration.event.name}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TicketIdConfirmationTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#b71959"),
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=23,
        spaceAfter=7 * mm,
    )
    body_style = ParagraphStyle(
        "TicketIdConfirmationBody",
        parent=styles["BodyText"],
        fontSize=11,
        leading=16,
        spaceAfter=3 * mm,
    )
    notice_style = ParagraphStyle(
        "TicketIdConfirmationNotice",
        parent=body_style,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#8f1747"),
        fontName="Helvetica-Bold",
        spaceBefore=7 * mm,
    )
    story = [
        Paragraph("Ticket ID Confirmation", title_style),
        Paragraph(
            "Soundarya Institute of Management and Science (SIMS)",
            body_style,
        ),
        Paragraph(f"<b>Event:</b> {escape(registration.event.name)}", body_style),
        Paragraph(f"<b>Applicant:</b> {escape(registration.buyer_name)}", body_style),
        Paragraph(
            f"<b>Ticket ID:</b> {escape(registration.ticket_id or 'Pending')}",
            body_style,
        ),
        Paragraph(
            f"<b>Registration reference:</b> {escape(registration.registration_code)}",
            body_style,
        ),
        Paragraph(
            f"<b>Payment verification status:</b> {escape(payment_status)}",
            body_style,
        ),
        Paragraph(
            "This document is not the final admission ticket and does not authorize event entry.",
            notice_style,
        ),
    ]
    document.build(story)
    return output.getvalue()
