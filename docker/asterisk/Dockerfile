# ==============================================================================
# Production Dockerfile for Asterisk PBX with AudioSocket Support
# ==============================================================================

FROM alpine:3.19

RUN apk add --no-cache \
    asterisk \
    asterisk-sample-config \
    asterisk-sounds-en \
    curl \
    bash

# Copy custom configurations
COPY extensions.conf /etc/asterisk/extensions.conf
COPY pjsip.conf /etc/asterisk/pjsip.conf

# SIP UDP port & RTP media ports
EXPOSE 5060/udp
EXPOSE 10000-10099/udp

# Run Asterisk in foreground
CMD ["asterisk", "-f", "-vvv"]
