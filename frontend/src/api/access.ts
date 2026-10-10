/** Private reviewer code stays in tab memory; never in URLs, storage or build env. */
let accessCode = ''
export function setAssessmentAccessCode(value: string) {
  accessCode = value.trim()
}
export function getAssessmentAccessCode() {
  return accessCode
}
