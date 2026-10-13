// Attach to /api/* viewer-request only. The origin accepts CloudFront traffic only.
// Overwrite any client-supplied header so login rate limits cannot trust spoofed IPs.
function handler(event) {
    var request = event.request;
    request.headers['x-lms-client-ip'] = {value: event.viewer.ip};
    return request;
}
