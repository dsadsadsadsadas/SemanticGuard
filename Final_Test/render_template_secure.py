# Secure Template Renderer
import html

def render_user_profile(username: str, bio: str) -> str:
    """Render user profile with HTML escaping"""
    # SECURE: HTML escaping prevents XSS
    safe_username = html.escape(username)
    safe_bio = html.escape(bio)
    
    return f"""
    <div class="profile">
        <h1>{safe_username}</h1>
        <p>{safe_bio}</p>
    </div>
    """
