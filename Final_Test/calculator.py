# Calculator Service
def calculate_expression(expr):
    # VULNERABLE: eval with user input
    result = eval(expr)
    return result

def process_formula(formula):
    # VULNERABLE: exec with user input
    exec(f"result = {formula}")
    return result
