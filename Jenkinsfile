pipeline{
	agent any
	options {
		parallelsAlwaysFailFast()
	}
	environment {
		IMAGE_NAME="hdavid0510/mjpeg-relay"
		IMAGE_TAG="dev"
		REGISTRY_CREDENTIALS=credentials('dockerhub-credential')
	}

	stages {
		stage('Build images') {
			parallel {
				stage('linux/386'){
					steps {
						echo 'Building linux/386 image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/386 -t $IMAGE_NAME:$IMAGE_TAG-i386 .'
					}
				}
				stage('linux/amd64'){
					steps {
						echo 'Building linux/amd64 image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/amd64 -t $IMAGE_NAME:$IMAGE_TAG-amd64 .'
					}
				}
				stage('linux/arm/v5'){
					steps {
						echo 'Building linux/arm/v5 image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/arm/v5 -t $IMAGE_NAME:$IMAGE_TAG-armv5 .'
					}
				}
				stage('linux/arm/v7'){
					steps {
						echo 'Building linux/arm/v7 image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/arm/v7 -t $IMAGE_NAME:$IMAGE_TAG-armv7 .'
					}
				}
				stage('linux/arm64'){
					steps {
						echo 'Building linux/arm64 image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/arm64 -t $IMAGE_NAME:$IMAGE_TAG-arm64 .'
					}
				}
				stage('linux/ppc64le'){
					steps {
						echo 'Building linux/ppc64le image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/ppc64le -t $IMAGE_NAME:$IMAGE_TAG-ppc64le .'
					}
				}
				stage('linux/s390x'){
					steps {
						echo 'Building linux/s390x image and pushing to DockerHub.'
						sh 'docker buildx build --platform linux/s390x -t $IMAGE_NAME:$IMAGE_TAG-s390x .'
					}
				}
			}
		}
		stage('Push multiarch image'){
			steps {
				echo 'Dockerhub login'
				sh 'echo $REGISTRY_CREDENTIALS_PSW | docker login -u $REGISTRY_CREDENTIALS_USR --password-stdin'
				echo "Running ${env.BUILD_ID} on ${env.JENKINS_URL}"
				echo "Building ${IMAGE_NAME} on branch ${IMAGE_TAG}"

				echo 'Pushing multiarch image to DockerHub'
				sh 'docker buildx build --push --platform linux/386,linux/amd64,linux/arm/v5,linux/arm/v7,linux/arm64,linux/ppc64le,linux/s390x -t $IMAGE_NAME:$IMAGE_TAG .'
			}
		}
	}

	post {
		always {
			sh 'docker logout'
		}
	}
}
