function mergeObjects(target, source) {
    // VULNERABLE: Prototype Pollution (no check for __proto__)
    for (let key in source) {
        if (typeof source[key] === 'object') {
            target[key] = mergeObjects(target[key] || {}, source[key]);
        } else {
            target[key] = source[key];
        }
    }
    return target;
}
