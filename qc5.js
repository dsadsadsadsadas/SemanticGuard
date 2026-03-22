/**
 * Live Test 3: Both layers pass, v1.0 handles it
 * Expected: Normal RAW THOUGHTS (v1.0 pipeline)
 * Layer 1: No deterministic violations
 * Layer 2: secureLogger is a registered sink - should ACCEPT
 * v1.0: Should also ACCEPT
 */

function logPatientData(patientId) {
    secureLogger.info(patientId);
    return "Logged";
}
