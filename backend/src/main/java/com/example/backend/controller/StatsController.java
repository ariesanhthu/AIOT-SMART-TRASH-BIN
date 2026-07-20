package com.example.backend.controller;

import com.example.backend.dto.response.DailyStatResponse;
import com.example.backend.dto.response.DailyStatSummaryResponse;
import com.example.backend.service.StatsService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/daily-stats")
public class StatsController {

    private final StatsService statsService;

    public StatsController(StatsService statsService) {
        this.statsService = statsService;
    }

    @GetMapping
    public List<DailyStatResponse> getDailyStats(
            @RequestParam String deviceId,
            @RequestParam String from,
            @RequestParam String to
    ) {
        return statsService.getDailyStats(deviceId, from, to);
    }

    @GetMapping("/summary")
    public DailyStatSummaryResponse getSummary(@RequestParam(required = false) String date) {
        return statsService.getSummary(date);
    }
}