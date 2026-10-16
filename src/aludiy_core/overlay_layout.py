"""Geometry-only label layout; text measurement is supplied by the viewport."""
def wrap_lines(lines, measure, max_width):
    """Wrap by Unicode characters; keep all IDs/numbers, no tiny fonts or ellipsis."""
    result=[]
    for line in lines:
        row=''
        for char in line:
            if row and measure(row+char)>max_width:
                result.append(row);row=''
            row+=char
        result.append(row)
    return result


def place_box(anchor, size, bounds):
    """Prefer beside the point, flip if needed, then clamp in visible viewport."""
    left,bottom,right,top=bounds; width,height=size
    x,y=anchor[0]+16,anchor[1]+18
    if x+width>right:x=anchor[0]-width-16
    if y+height>top:y=anchor[1]-height-18
    return max(left,min(x,right-width)),max(bottom,min(y,top-height))
