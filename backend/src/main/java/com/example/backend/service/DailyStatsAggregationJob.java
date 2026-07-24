package com.example.backend.service;

/**
 * The DailyStatsAggregationJob has been removed.
 *
 * <p>Daily stats are now updated <strong>synchronously at event ingestion time</strong>
 * inside {@link EventService#ingestEvent}, which calls
 * {@link EventService#upsertDailyStat} within the same transaction.
 *
 * <p>This eliminates the need for a periodic Firestore-polling job and guarantees
 * that stats are consistent with the events table at all times without a
 * separate scheduler process.
 *
 * <p>This class is intentionally left as a stub comment to document the migration.
 * It can be deleted entirely.
 */
public final class DailyStatsAggregationJob {
    // Intentionally empty — see EventService#ingestEvent
    private DailyStatsAggregationJob() {}
}