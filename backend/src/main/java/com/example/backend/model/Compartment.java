package com.example.backend.model;

import com.google.cloud.firestore.annotation.PropertyName;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class Compartment {
    private Double threshold;

    @PropertyName("fill_percent")
    private Double fillPercent;

    private String status;
}