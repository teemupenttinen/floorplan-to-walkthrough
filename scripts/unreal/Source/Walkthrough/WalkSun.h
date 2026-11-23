#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WalkSun.generated.h"

class UDirectionalLightComponent;
class ULightComponent;

/**
 * Sun, exposure, white balance and lamps of the walkthrough. import_manifest.py spawns one into the level.
 * The sun follows the NOAA solar position equations for the site's latitude and longitude, so a given day
 * and clock time give the real sun direction (golden hour, winter light, midsummer evening).
 *
 * Model axes: ModelNorthDeg is the direction of true north in the model, in degrees counter-clockwise from
 * model +x (90 = model +y points north). Unreal = (100 x, -100 y, 100 z) of the model.
 */
UCLASS()
class WALKTHROUGH_API AWalkSun : public AActor
{
	GENERATED_BODY()

public:
	AWalkSun();

	/** Site latitude and longitude in degrees (north and east positive). City-level accuracy is enough. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	double Latitude = 51.5;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	double Longitude = 0.0;

	/** Standard (winter) time zone, hours east of UTC. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float UtcOffset = 0.f;

	/** Clock time is one hour ahead from SummerStartDay to SummerEndDay (day of the year, 1..365). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	bool bSummerTime = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	int32 SummerStartDay = 87;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	int32 SummerEndDay = 300;

	/** True north in the model, degrees counter-clockwise from model +x. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float ModelNorthDeg = 90.f;

	/** Clock time (hours) and day of the year at the start. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float Hour = 15.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	int32 Day = 172;

	/** Sun illuminance at high noon (lux). Physical units: auto exposure handles the range. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float SunLux = 75000.f;

	/** Exposure offset applied at start (EV). -1 reads closer to photographs of bright interiors. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float DefaultExposure = -1.f;

	/** Exposure offset outdoors (EV), on top of SetExposure: the auto exposure is tuned for rooms with bright
	 *  windows and over-brightens facades under an open sky. "Outdoors" = nothing above the camera within 30 m. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float OutdoorExposure = -1.f;
	virtual void Tick(float DeltaSeconds) override;
	/** Lamp colour temperature (K). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	float LampKelvin = 3000.f;

	/** Path of the material parameter collection with the scalar LightsOn (lamp glow). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sun")
	FString LightsCollection = TEXT("/Game/Walkthrough/Materials/MPC_Lights.MPC_Lights");

	UFUNCTION(BlueprintCallable, Category = "Sun")
	void SetHour(float NewHour);

	UFUNCTION(BlueprintCallable, Category = "Sun")
	void SetDay(int32 NewDay);

	float GetHour() const { return Hour; }
	int32 GetDay() const { return Day; }

	/** Exposure offset in stops, on top of the level's auto exposure bias. */
	UFUNCTION(BlueprintCallable, Category = "Sun")
	void SetExposure(float Ev);

	/** Daylight white balance (K). 6500 is neutral; higher reads warmer, lower cooler. */
	UFUNCTION(BlueprintCallable, Category = "Sun")
	void SetDayWhite(float Kelvin);

	/** All room lights (actors tagged CeilingLight) on or off. */
	UFUNCTION(BlueprintCallable, Category = "Sun")
	void SetLamps(bool bOn);

	UFUNCTION(BlueprintCallable, Category = "Sun")
	void ToggleLamps() { SetLamps(!bLampsOn); }

	/** Only the room light nearest to At (Unreal cm) on, at Level 0..1 (bathrooms without windows). */
	UFUNCTION(BlueprintCallable, Category = "Sun")
	void SetOnlyRoomAt(const FVector& At, float Level);

	bool AreLampsOn() const { return bLampsOn; }

	/** Sun elevation in degrees (negative at night). */
	float GetSunElevation() const { return SunEl; }

	virtual void BeginPlay() override;

private:
	float CurrentEv = 0.f;
	float OutdoorBlend = 0.f;
	float OutdoorCheck = 0.f;
	bool bOutdoor = false;
	void ApplyExposure();
	void ApplySun();
	void ApplyLampGlow(float Level);
	void FindLamps();
	void SolarPosition(int32 InDay, float InHour, double& El, double& Az) const;

	UPROPERTY()
	TObjectPtr<UDirectionalLightComponent> Sun;

	struct FLamp
	{
		TWeakObjectPtr<ULightComponent> Light;
		float Intensity = 0.f;
		FVector Location = FVector::ZeroVector;
	};
	TArray<FLamp> Lamps;
	float BaseBias = 0.f;
	float SunEl = 0.f;
	bool bLampsOn = false;
};
