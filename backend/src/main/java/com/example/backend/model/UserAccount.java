package com.example.backend.model;

import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class UserAccount {
    private String email;
    private String role;
}