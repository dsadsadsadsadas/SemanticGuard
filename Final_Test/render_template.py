# Template Renderer
def render_user_profile(username, bio):
    # VULNERABLE: XSS - no escaping
    html = f"""
    <div class="profile">
        <h1>{username}</h1>
        <p>{bio}</p>
    </div>
    """
    return html
