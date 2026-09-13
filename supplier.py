import io
import re
from collections import defaultdict

from openpyxl import load_workbook


SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)")


def norm_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    ).lower()


def norm_model(value):
    text = (
        str(value or "")
        .replace("®", "")
        .strip()
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    )


def norm_size(value):
    if value is None:
        return None

    text = (
        str(value)
        .strip()
        .replace(",", ".")
        .replace("-", ".")
    )

    match = SIZE_RE.match(text)

    if not match:
        return None

    number = float(match.group(1))

    if number.is_integer():
        return str(int(number))

    return f"{number:.1f}"


def qty(value):
    """
    Supplier quantity parser.

    Examples:
    5       -> 5
    5.0     -> 5
    "5"     -> 5
    "1 (49)" -> 1

    The supplier total/formula column is never read.
    """

    if value is None or value == "":
        return 0

    if isinstance(value, (int, float)):
        return int(value)

    match = re.match(
        r"\s*(-?\d+)",
        str(value),
    )

    if not match:
        return 0

    return int(match.group(1))


def is_model_header(row):
    """
    A real supplier model header contains the complete size grid.

    This deliberately requires many size labels.

    Important:
    stock cells such as "1 (49)" must NOT be mistaken
    for a model header.
    """

    if len(row) < 3:
        return False

    model_cell = row[1]

    if not model_cell:
        return False

    parsed_sizes = []

    # C:Y = supplier size columns.
    # Z is the displayed total/formula column and is ignored.
    for cell in row[2:25]:
        if not isinstance(cell, str):
            continue

        # Genuine size headers look like:
        # "36 (3)", "42.5 (8.5)", etc.
        if "(" not in cell:
            continue

        size = norm_size(cell)

        if size:
            parsed_sizes.append(size)

    # A supplier model header has a long ordered size grid.
    # Requiring these characteristics prevents quantity cells
    # like "1 (49)" from being treated as headers.
    if len(parsed_sizes) < 10:
        return False

    if parsed_sizes[0] != "36":
        return False

    if "42" not in parsed_sizes:
        return False

    if "47" not in parsed_sizes:
        return False

    return True


def clean_color_and_width(value):
    """
    Returns:
        color, width

    Examples:
        "dark brown*"   -> ("dark brown", "standard")
        "dark brown W"  -> ("dark brown", "wide")
        "ranger green W*" also handled safely.
    """

    raw = str(value or "").strip()

    # Lithuanian marker does not create another offer.
    # It must be summed into the same model/color/width/size.
    clean = raw.replace("*", "").strip()

    wide = bool(
        re.search(
            r"\bW\s*$",
            clean,
            flags=re.IGNORECASE,
        )
    )

    if wide:
        clean = re.sub(
            r"\bW\s*$",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()

    color = norm_text(clean)
    width = "wide" if wide else "standard"

    return color, width


def parse_xlsx_bytes(data: bytes):
    """
    Parse LOWA supplier XLSX.

    Rules:
    - use sheet LOWA only;
    - ignore supplier displayed totals completely;
    - use only per-size quantity cells;
    - sum Latvia + Lithuania (*) rows;
    - keep Wide as a separate offer;
    - blank size cells mean zero;
    - strings such as "1 (49)" use leading quantity only.
    """

    workbook = load_workbook(
        io.BytesIO(data),
        data_only=True,
        read_only=True,
    )

    if "LOWA" not in workbook.sheetnames:
        raise RuntimeError(
            "Supplier workbook does not contain LOWA sheet"
        )

    sheet = workbook["LOWA"]

    rows = list(
        sheet.iter_rows(
            values_only=True
        )
    )

    stock = defaultdict(
        lambda: defaultdict(int)
    )

    metadata = {}

    row_index = 0

    while row_index < len(rows):
        row = rows[row_index]

        if not is_model_header(row):
            row_index += 1
            continue

        model = norm_model(row[1])

        # Only C:Y.
        # The total/formula column is intentionally excluded.
        sizes = [
            norm_size(cell)
            for cell in row[2:25]
        ]

        row_index += 1

        while row_index < len(rows):
            current = rows[row_index]

            # Next model begins.
            if is_model_header(current):
                break

            # Fully blank separator row ends current model block.
            if not any(
                value not in (None, "")
                for value in current[:25]
            ):
                break

            color_cell = (
                current[1]
                if len(current) > 1
                else None
            )

            color_raw = str(
                color_cell or ""
            ).strip()

            # Ignore rows without a color name.
            if not color_raw:
                row_index += 1
                continue

            color, width = (
                clean_color_and_width(
                    color_raw
                )
            )

            if not color:
                row_index += 1
                continue

            key = (
                model,
                color,
                width,
            )

            # Read only size cells.
            # Never read the total/formula cell.
            for column_index, size in enumerate(
                sizes,
                start=2,
            ):
                if size is None:
                    continue

                if column_index >= len(current):
                    continue

                stock[key][size] += qty(
                    current[column_index]
                )

            metadata[key] = {
                "model": model,
                "color": color,
                "width": width,
            }

            row_index += 1

        # Do not manually advance here.
        # Outer loop will handle next header or separator.

    result = []

    for key, quantities in stock.items():
        ordered_stock = dict(
            sorted(
                quantities.items(),
                key=lambda item: float(
                    item[0]
                ),
            )
        )

        result.append(
            {
                **metadata[key],
                "stock": ordered_stock,
            }
        )

    result.sort(
        key=lambda row: (
            row["model"],
            row["color"],
            row["width"],
        )
    )

    return result
