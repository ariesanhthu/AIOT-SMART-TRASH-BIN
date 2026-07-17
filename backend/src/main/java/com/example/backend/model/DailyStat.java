package com.example.backend.model;

import com.google.cloud.firestore.annotation.PropertyName;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class DailyStat {
    @PropertyName("device_id")
    private String deviceId;

    private String date;

    @PropertyName("organic_count")
    private Long organicCount;

    @PropertyName("paper_count")
    private Long paperCount;

    @PropertyName("plastic_count")
    private Long plasticCount;

    @PropertyName("total_count")
    private Long totalCount;
}