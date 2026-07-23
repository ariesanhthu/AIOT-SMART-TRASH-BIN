package com.example.backend.controller;

import com.example.backend.dto.response.DailyStatResponse;
import com.example.backend.dto.response.DailyStatSummaryResponse;
import com.example.backend.service.StatsService;
import com.example.backend.dto.response.DeviceRankResponse;
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
            @RequestParam(required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(required = false) String date
    ) {
        if (date != null && !date.isBlank()) {
            from = date;
            to = date;
        }
        return statsService.getDailyStats(deviceId, from, to);
    }

    @GetMapping("/summary")
    public DailyStatSummaryResponse getSummary(@RequestParam(defaultValue = "1") int days) {
        return statsService.getSummary(days);
    }

    @GetMapping("/ranking")
    public List<DeviceRankResponse> getRanking(@RequestParam(defaultValue = "7") int days) {
        return statsService.getRanking(days);
    }
}