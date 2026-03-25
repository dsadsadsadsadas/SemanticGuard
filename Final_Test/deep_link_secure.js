function handleDeepLink(url) {
    // SAFE: Strict protocol checking for Deep Links
    if (url.startsWith('https://') || url.startsWith('app://')) {
        window.location.href = url;
    }
}
