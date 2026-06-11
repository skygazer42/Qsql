def is_text_pdf(pdf_path):
    import fitz

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    if total_pages == 0:
        return False

    text_pages = 0
    for page_num in range(total_pages):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():
            text_pages += 1

    text_ratio = text_pages / total_pages
    return text_ratio > 0.5
