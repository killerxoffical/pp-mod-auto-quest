package com.vareon.playquest;

import android.app.job.JobParameters;
import android.app.job.JobService;

public class PushPollJobService extends JobService {

    @Override
    public boolean onStartJob(final JobParameters params) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    PushHelper.pollEdgeNotificationsSync(getApplicationContext());
                } catch (Throwable ignored) {
                } finally {
                    try {
                        jobFinished(params, false);
                    } catch (Throwable ignored) {
                    }
                }
            }
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
