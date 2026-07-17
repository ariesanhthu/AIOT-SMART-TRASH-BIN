package com.example.backend.exception;

public class InvalidProvisioningSecretException extends RuntimeException {
    public InvalidProvisioningSecretException() {
        super("Thiếu hoặc sai provisioning secret khi cấp token cho thiết bị");
    }
}
