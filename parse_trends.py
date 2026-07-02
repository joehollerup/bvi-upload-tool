#!/usr/bin/env python3
"""Parse Google Trends CSV exports and print monthly brand vs. competitor indices."""

FILES = [
    "KEEN - Google Trends Export 1.csv",
    "KEEN - Google Trends Export 2.csv",
]


def parse(path):
    with open(path) as f:
        lines = [line.strip() for line in f if line.strip()]

    rows = [[cell.strip().strip('"') for cell in line.split(",")] for line in lines]
    header = rows[0]
    brand = header[1]          # first data column = client brand
    others = header[2:]        # competitors / categories

    print(f"\n=== {path} ===")
    print(f"Brand: {brand}  |  Compared to: {', '.join(others)}")
    for row in rows[1:]:
        month = row[0]
        brand_val = row[1]
        other_vals = ", ".join(
            f"{name}={val}" for name, val in zip(others, row[2:])
        )
        print(f"{month}  {brand}={brand_val}  {other_vals}")


def load():
    """Return {'comp': {YYYY-MM: {name: index}}, 'cat': {YYYY-MM: {name: index}}}.

    'comp' = Export 1 (brand vs competitors); 'cat' = Export 2 (brand vs category).
    """
    out = {}
    for key, path in zip(["comp", "cat"], FILES):
        with open(path) as f:
            lines = [line.strip() for line in f if line.strip()]
        rows = [[c.strip().strip('"') for c in line.split(",")] for line in lines]
        header = rows[0]
        table = {}
        for row in rows[1:]:
            month = row[0][:7]  # "2024-10-01" -> "2024-10"
            table[month] = {header[i]: int(row[i]) for i in range(1, len(header))}
        out[key] = table
    return out


def load_from(paths):
    """Like load() but accepts explicit [comp_path, cat_path] instead of hardcoded FILES."""
    out = {}
    for key, path in zip(["comp", "cat"], paths):
        with open(path) as f:
            lines = [line.strip() for line in f if line.strip()]
        rows = [[c.strip().strip('"') for c in line.split(",")] for line in lines]
        header = rows[0]
        table = {}
        for row in rows[1:]:
            month = row[0][:7]
            table[month] = {header[i]: int(row[i]) for i in range(1, len(header))}
        out[key] = table
    return out


def main():
    for path in FILES:
        parse(path)


if __name__ == "__main__":
    main()
