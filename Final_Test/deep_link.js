function handleDeepLink(url) {
    // VULNERABLE: Insecure Deep Linking allowing XSS via javascript: URIs
    window.location.href = url;
}
