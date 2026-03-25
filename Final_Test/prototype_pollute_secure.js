function mergeObjects(target, source) {
    // SAFE: Prototype Pollution defense
    for (let key in source) {
        if (key === '__proto__' || key === 'constructor') continue;
        if (typeof source[key] === 'object') {
            target[key] = mergeObjects(target[key] || {}, source[key]);
        } else {
            target[key] = source[key];
        }
    }
    return target;
}
