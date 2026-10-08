from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer


class TicketQr(Flowable):
    def __init__(self, token, size=46 * mm):
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


def generate_tickets_pdf(tickets):
    tickets = list(tickets)
    if not tickets:
        raise ValueError("A ticket PDF requires at least one ticket.")

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A5,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Tickets for {tickets[0].registration.event.name}",
        pageCompression=0,
    )
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TicketTitle",
        parent=base_styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#8f174c"),
        fontSize=18,
        leading=23,
        spaceAfter=5 * mm,
    )
    center_style = ParagraphStyle(
        "TicketCenter",
        parent=base_styles["BodyText"],
        alignment=TA_CENTER,
        leading=15,
    )
    label_style = ParagraphStyle(
        "TicketLabel",
        parent=base_styles["BodyText"],
        alignment=TA_LEFT,
        leading=16,
    )

    story = []
    for index, ticket in enumerate(tickets):
        event = ticket.registration.event
        details = [
            Paragraph(escape(event.name), title_style),
            Paragraph(
                f"{escape(event.venue)} · {escape(event.city)}<br/>"
                f"{event.start_at:%d %B %Y} · {event.start_at:%I:%M %p}",
                center_style,
            ),
            Spacer(1, 6 * mm),
            TicketQr(ticket.token),
            Spacer(1, 5 * mm),
            Paragraph(f"<b>Attendee</b>: {escape(ticket.attendee_name or ticket.registration.buyer_name)}", label_style),
            Paragraph(f"<b>Ticket type</b>: {escape(ticket.registration.ticket_tier.name)}", label_style),
            Paragraph(f"<b>Ticket ID</b>: {escape(str(ticket.id))}", label_style),
            Paragraph(f"<b>Registration ID</b>: {escape(str(ticket.registration_id))}", label_style),
            Paragraph("Present this QR code at the event entrance.", center_style),
        ]
        story.extend(details)
        if index < len(tickets) - 1:
            story.append(PageBreak())

    document.build(story)
    return output.getvalue()
