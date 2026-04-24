import time

last_render_line_count = 0

def render(msg=""):
    global last_render_line_count
    lines = [
        "",
        "Line 1",
        "Line 2",
        "Line 3",
        msg,
    ]
    total_lines = max(last_render_line_count, len(lines))

    if last_render_line_count > 1:
        print(f"\r\033[{last_render_line_count - 1}F", end="")
    elif last_render_line_count == 1:
        print("\r", end="")

    for index in range(total_lines):
        line = lines[index] if index < len(lines) else ""
        end = "\n" if index < total_lines - 1 else ""
        print(f"\033[2K{line}", end=end)

    last_render_line_count = len(lines)
    print("", end="", flush=True)

render("First render")
time.sleep(1)
print("\n   [Exec] some command")
time.sleep(1)
render("Second render")
print("\nDone")
