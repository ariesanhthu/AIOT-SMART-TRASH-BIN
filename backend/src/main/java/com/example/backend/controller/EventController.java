package com.example.backend.controller;

import com.example.backend.dto.request.IngestEventRequest;
import com.example.backend.dto.response.EventResponse;
import com.example.backend.service.EventService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/devices/{deviceId}/events")
public class EventController {

    private final EventService eventService;

    public EventController(EventService eventService) {
        this.eventService = eventService;
    }

    /**
     * ESP32 firmware POSTs events here using its Device Token
     * (Authorization: Bearer <device JWT>).
     *
     * DeviceTokenFilter authenticates the request before it reaches this
     * method. FirebaseAuthFilter excludes this path.
     */
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public EventResponse ingestEvent(
            @PathVariable String deviceId,
            @RequestBody IngestEventRequest request
    ) {
        return eventService.ingestEvent(deviceId, request);
    }

    /**
     * Dashboard reads event history for a device.
     * GET is open (no auth required per FirebaseAuthFilter policy).
     */
    @GetMapping
    public List<EventResponse> getEvents(
            @PathVariable String deviceId,
            @RequestParam(required = false) String eventType,
            @RequestParam(defaultValue = "50") int limit
    ) {
        return eventService.getEvents(deviceId, eventType, limit);
    }

    /**
     * Dashboard resolves a FULL_ALERT event.
     * Requires Firebase ID Token (handled by FirebaseAuthFilter).
     */
    @PatchMapping("/{eventId}/resolve")
    public ResponseEntity<Void> resolveAlert(
            @PathVariable String deviceId,
            @PathVariable String eventId,
            HttpServletRequest request
    ) {
        String email = (String) request.getAttribute("email");
        eventService.resolveAlert(deviceId, eventId, email);
        return ResponseEntity.noContent().build();
    }
}
