package com.example.backend.model;

import com.google.cloud.firestore.annotation.PropertyName;
import lombok.NoArgsConstructor;

@NoArgsConstructor
public class DailyStat {
    private String deviceId;
    private String date;
    private Long organicCount;
    private Long paperCount;
    private Long plasticCount;
    private Long totalCount;

    @PropertyName("device_id")
    public String getDeviceId() { return deviceId; }
    @PropertyName("device_id")
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getDate() { return date; }
    public void setDate(String date) { this.date = date; }

    @PropertyName("organic_count")
    public Long getOrganicCount() { return organicCount; }
    @PropertyName("organic_count")
    public void setOrganicCount(Long organicCount) { this.organicCount = organicCount; }

    @PropertyName("paper_count")
    public Long getPaperCount() { return paperCount; }
    @PropertyName("paper_count")
    public void setPaperCount(Long paperCount) { this.paperCount = paperCount; }

    @PropertyName("plastic_count")
    public Long getPlasticCount() { return plasticCount; }
    @PropertyName("plastic_count")
    public void setPlasticCount(Long plasticCount) { this.plasticCount = plasticCount; }

    @PropertyName("total_count")
    public Long getTotalCount() { return totalCount; }
    @PropertyName("total_count")
    public void setTotalCount(Long totalCount) { this.totalCount = totalCount; }
}