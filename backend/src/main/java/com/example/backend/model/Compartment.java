package com.example.backend.model;

import com.google.cloud.firestore.annotation.PropertyName;
import lombok.NoArgsConstructor;

@NoArgsConstructor
public class Compartment {
    private Double threshold;
    private Double fillPercent;
    private String status;

    public Double getThreshold() { return threshold; }
    public void setThreshold(Double threshold) { this.threshold = threshold; }

    @PropertyName("fill_percent")
    public Double getFillPercent() { return fillPercent; }
    @PropertyName("fill_percent")
    public void setFillPercent(Double fillPercent) { this.fillPercent = fillPercent; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}